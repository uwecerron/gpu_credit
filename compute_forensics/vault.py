"""sUSDai vault mechanics (RQ2, RQ5): NAV per share, share supply, cash yield,
the redemption queue, and USDai mint/burn flows. All inputs are decoded events.
"""
from __future__ import annotations

import statistics
from collections import defaultdict
from datetime import date, datetime, timedelta

from . import registry as R
from .events import Ev

WAD = 1e18


def _day(ts: str) -> str:
    return ts[:10]


def nav_series(events: list[Ev]) -> dict[str, float]:
    """Daily median of assets/shares over sUSDai Deposit events (the vault's
    deposit-side NAV, which includes accrued loan interest)."""
    by_day = defaultdict(list)
    for e in events:
        if e.name == "sUSDai.Deposit" and e.f["shares"] > 10 ** 15:   # ignore dust deposits
            by_day[_day(e.time)].append(e.f["assets"] / e.f["shares"])
    return {d: statistics.median(v) for d, v in sorted(by_day.items())}


def fill_daily(series: dict[str, float], start: str, end: str) -> dict[str, float]:
    """Forward-fill a sparse daily series over [start, end]."""
    out, last = {}, None
    d, stop = date.fromisoformat(start), date.fromisoformat(end)
    while d <= stop:
        k = d.isoformat()
        last = series.get(k, last)
        if last is not None:
            out[k] = last
        d += timedelta(days=1)
    return out


def supply_series(events: list[Ev]) -> dict[str, float]:
    """Global sUSDai share supply by day: minted on Deposit, burned at
    requestRedeem (ERC-7540 burns at request). Bridging moves shares between
    chains without changing the global total, so it does not enter here."""
    delta = defaultdict(float)
    for e in events:
        if e.name == "sUSDai.Deposit":
            delta[_day(e.time)] += e.f["shares"] / WAD
        elif e.name == "sUSDai.RedeemRequest":
            delta[_day(e.time)] -= e.f["shares"] / WAD
    out, run = {}, 0.0
    for d in sorted(delta):
        run += delta[d]
        out[d] = run
    return out


def annualized(nav: dict[str, float], start: str, end: str) -> float | None:
    a, b = nav.get(start), nav.get(end)
    if not a or not b:
        return None
    days = (date.fromisoformat(end) - date.fromisoformat(start)).days
    return (b / a) ** (365 / days) - 1 if days > 0 else None


def yield_accrued(nav_daily: dict[str, float], supply_daily: dict[str, float]) -> dict[str, float]:
    """USD value accrued to holders per month: sum_d supply_d * (NAV_{d+1} - NAV_d)."""
    days = sorted(set(nav_daily) & set(supply_daily))
    out = defaultdict(float)
    for d0, d1 in zip(days, days[1:]):
        out[d1[:7]] += supply_daily[d0] * (nav_daily[d1] - nav_daily[d0])
    return dict(out)


LOAN_ROUTER_ADMIN_FEE = 0.10


def cash_yield(events: list[Ev], hash_ccy: dict[str, str]) -> dict[str, dict[str, float]]:
    """Cash that actually reached the vault per month, by source. Loan amounts are
    scaled by the currency of the terms hash they were paid under."""
    out = defaultdict(lambda: defaultdict(float))
    for e in events:
        m = e.time[:7]
        if e.name == "LR.LenderRepaid" and e.f["lender"] == R.SUSDAI:
            unit = 10 ** R.DECIMALS.get(hash_ccy.get(e.f["loan_terms_hash"], R.USDAI), 18)
            out[m]["loan_interest"] += e.f["interest"] / unit
        elif e.name == "sUSDai.BaseYieldDeposited":
            # amount credited to the vault; the 10% admin fee is reported separately
            out[m]["base_yield"] += e.f["deposited_amount"] / WAD
        elif e.name in ("sUSDai.LoanEscrowTimelockWithdrawn", "sUSDai.LoanEscrowTimelockCancelled"):
            # escrow interest; the router admin fee (10%, seen as a transfer to the
            # admin fee recipient in the same tx) is deducted before the vault is credited
            out[m]["escrow_interest"] += e.f["interest_amount"] / WAD * (1 - LOAN_ROUTER_ADMIN_FEE)
        elif e.name == "LR2.FeePaid" and e.f["recipient"] == R.SUSDAI:
            unit = 10 ** R.DECIMALS.get(hash_ccy.get(e.f["loan_terms_hash"], R.USDAI), 18)
            out[m]["fees"] += e.f["amount"] / unit
    return {k: dict(v) for k, v in sorted(out.items())}


def base_yield_admin_fees(events: list[Ev]) -> float:
    return sum(e.f["admin_fee"] / WAD for e in events if e.name == "sUSDai.BaseYieldDeposited")


def usdai_flows(events: list[Ev]) -> dict:
    """USDai mints (deposits) and burns (withdrawals) by token and month."""
    by_tok = defaultdict(lambda: {"mint_usd": 0.0, "burn_usd": 0.0, "n_mint": 0, "n_burn": 0})
    monthly = defaultdict(lambda: {"mint": 0.0, "burn": 0.0})
    callers = defaultdict(float)
    for e in events:
        if e.name == "USDai.Deposited":
            v = e.f["mint_amount"] / WAD
            by_tok[e.f["deposit_token"]]["mint_usd"] += v
            by_tok[e.f["deposit_token"]]["n_mint"] += 1
            monthly[e.time[:7]]["mint"] += v
            callers[e.f["caller"]] += v
        elif e.name == "USDai.Withdrawn":
            v = e.f["usdai_amount"] / WAD
            by_tok[e.f["withdraw_token"]]["burn_usd"] += v
            by_tok[e.f["withdraw_token"]]["n_burn"] += 1
            monthly[e.time[:7]]["burn"] += v
    return {"by_token": dict(by_tok), "monthly": dict(sorted(monthly.items())), "mint_callers": dict(callers)}


def redemption_queue(events: list[Ev]) -> dict:
    """Requests, fulfilments and wait times. A request is matched to the
    RedemptionProcessed events that carry its id (partial fills allowed)."""
    req = {}
    for e in events:
        if e.name == "sUSDai.RedeemRequest":
            req[e.f["request_id"]] = {"t": e.time, "shares": e.f["shares"] / WAD, "controller": e.f["controller"],
                                      "filled": 0.0, "paid": 0.0, "done": None}
    batches = []
    for e in events:
        if e.name == "sUSDai.RedemptionProcessed":
            r = req.get(e.f["redemption_id"])
            if r is None:
                continue
            r["filled"] += e.f["fulfilled_shares"] / WAD
            r["paid"] += e.f["amount"] / WAD
            if e.f["pending_shares"] == 0:
                r["done"] = e.time
        elif e.name == "sUSDai.RedemptionsServiced":
            batches.append({"t": e.time, "shares": e.f["shares"] / WAD, "amount": e.f["amount"] / WAD,
                            "all": bool(e.f["all_serviced"])})
    waits = []
    for r in req.values():
        if r["done"]:
            t0 = datetime.fromisoformat(r["t"].replace("Z", "+00:00"))
            t1 = datetime.fromisoformat(r["done"].replace("Z", "+00:00"))
            waits.append((t1 - t0).total_seconds() / 86400)
    pending = sum(max(r["shares"] - r["filled"], 0.0) for r in req.values())
    weekly = defaultdict(float)
    for r in req.values():
        d = date.fromisoformat(r["t"][:10])
        weekly[(d - timedelta(days=d.weekday())).isoformat()] += r["shares"]
    return {"requests": len(req), "requested_shares": sum(r["shares"] for r in req.values()),
            "filled_shares": sum(r["filled"] for r in req.values()), "paid_usdai": sum(r["paid"] for r in req.values()),
            "pending_shares": pending, "completed": len(waits),
            "wait_days_median": statistics.median(waits) if waits else None,
            "wait_days_p90": (sorted(waits)[int(0.9 * (len(waits) - 1))] if waits else None),
            "wait_days_max": max(waits) if waits else None,
            "batches": batches, "weekly_requests": dict(sorted(weekly.items())),
            "unique_redeemers": len({r["controller"] for r in req.values()})}


def spearman(x: list[float], y: list[float]) -> float | None:
    n = len(x)
    if n < 3:
        return None

    def ranks(v):
        order = sorted(range(n), key=lambda i: v[i])
        r = [0.0] * n
        i = 0
        while i < n:
            j = i
            while j + 1 < n and v[order[j + 1]] == v[order[i]]:
                j += 1
            for k in range(i, j + 1):
                r[order[k]] = (i + j) / 2
            i = j + 1
        return r
    rx, ry = ranks(x), ranks(y)
    mx, my = sum(rx) / n, sum(ry) / n
    cov = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    vx = sum((a - mx) ** 2 for a in rx) ** 0.5
    vy = sum((b - my) ** 2 for b in ry) ** 0.5
    return cov / (vx * vy) if vx and vy else None


WM = "0x437cc33344a0b27a429f795ff6b469c72698b291"


def base_yield_events(events: list[Ev]) -> list[dict]:
    """Each BaseYieldDeposited with its funding source, for the one-off split."""
    by_tx: dict[str, list[Ev]] = defaultdict(list)
    for e in events:
        by_tx[e.tx].append(e)
    out = []
    for e in events:
        if e.name != "sUSDai.BaseYieldDeposited":
            continue
        peers = by_tx[e.tx]
        src = ("pyusd_harvest" if any(p.name == "USDai.Harvested" for p in peers) else
               "wm" if any(p.name == "USDai.Deposited" and p.f.get("deposit_token") == WM for p in peers) else "other")
        out.append({"time": e.time, "tx": e.tx, "source": src, "usd": e.f["deposited_amount"] / WAD})
    return out


def base_yield_by_source(events: list[Ev]) -> dict[str, float]:
    """Split vault base yield by what funded it, using the other events in the same tx:
    a USDai.Harvested in the tx means PYUSD issuer incentives paid out of the Base Yield
    Escrow; a USDai.Deposited of wM (M^0's wrapped M) means the yield was minted from wM."""
    by_tx: dict[str, list[Ev]] = defaultdict(list)
    for e in events:
        by_tx[e.tx].append(e)
    out = defaultdict(float)
    for e in events:
        if e.name != "sUSDai.BaseYieldDeposited":
            continue
        peers = by_tx[e.tx]
        if any(p.name == "USDai.Harvested" for p in peers):
            src = "pyusd_harvest"
        elif any(p.name == "USDai.Deposited" and p.f.get("deposit_token") == WM for p in peers):
            src = "wm"
        else:
            src = "other"
        out[src] += e.f["deposited_amount"] / WAD
    return dict(out)
