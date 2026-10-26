"""Offline analysis: data/frozen -> results/, paper/figures/, paper/generated/.
Every number quoted in the paper is written to paper/generated/numbers.tex by
this module, so the text cannot drift from the data."""
from __future__ import annotations

import csv
import gzip
import json
import logging
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

from . import figures, holders as H, loans as L, registry as R, vault as V
from .events import from_protocol_txs, from_scans, merge
from .freeze import verify

log = logging.getLogger("compute_forensics")


def _load(p: Path):
    with gzip.open(p, "rt", encoding="utf-8") as fh:
        return json.load(fh)


def _csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("")
        return
    keys = list(rows[0].keys())
    with path.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)


def _gpu_weekly(external: Path) -> list[tuple[str, float]]:
    p = external / "getdeploying_weekly.json"
    if not p.exists():
        return []
    d = json.loads(p.read_text())
    rows = [r for r in d["data"] if r["gpu_slug"] == "nvidia-h100" and r["billing_type"] == "ON_DEMAND"]
    return sorted((r["date"], r["median_price"]) for r in rows)


def repayment_funding(events, loans_meta, accounts) -> dict:
    """Who submitted each LoanRepaid. Borrowers are contract accounts, so the
    submitter is almost always an EOA acting for the borrower, and the
    "third party / operator" bucket is mostly those signers. Kept for the CSVs;
    not used in the paper."""
    ra = loans_meta["reserve_accounts"]
    payers = defaultdict(lambda: {"n": 0, "interest": 0.0})
    by_kind = defaultdict(float)
    for e in events:
        if e.name != "LR.LoanRepaid":
            continue
        unit = 10 ** R.DECIMALS.get(loans_meta["hash_ccy"].get(e.f["loan_terms_hash"], R.USDAI), 18)
        payer = e.tx_from
        kind = ("reserve account" if payer in ra else
                "borrower" if payer == e.f["borrower"] else
                "underlying borrower" if ra.get(e.f["borrower"]) == payer else "third party / operator")
        payers[payer]["n"] += 1
        payers[payer]["interest"] += e.f["interest"] / unit
        by_kind[kind] += e.f["interest"] / unit
    return {"by_payer_kind": dict(by_kind), "payers": {k: dict(v) for k, v in payers.items()}}


def principal_destinations(loans: dict, accounts: dict, horizon_days: int = 30) -> dict:
    """For V1 originations, follow the borrower's outgoing transfers of the loan
    currency in the following `horizon_days`."""
    txs_by_borrower = accounts.get("borrower_txs") or {}
    from .abi import decode_log
    dest = defaultdict(float)
    followed = 0
    for ln in loans.values():
        hist = txs_by_borrower.get(ln.borrower)
        if not hist or ln.principal < 1000:
            continue
        followed += 1
        t0 = ln.originated
        t1 = (date.fromisoformat(t0[:10]) + timedelta(days=horizon_days)).isoformat()
        for t in hist:
            if not (t0 <= t["t"] <= t1):
                continue
            for lg in t["logs"]:
                d = decode_log(lg["tp"], lg["d"], only={"ERC20.Transfer"})
                if not d or lg["a"] != ln.currency:
                    continue
                f = d[1]
                if f["from"] != ln.borrower:
                    continue
                dest[f["to"]] += f["value"] / 10 ** R.DECIMALS.get(ln.currency, 18)
    return {"loans_followed": followed, "destinations": dict(sorted(dest.items(), key=lambda kv: -kv[1]))}


def loan_book_health(real: dict, events, end: str) -> dict:
    """Maturity profile and payment currency of the active book."""
    last = {}
    for e in events:
        if e.name == "LR.LoanRepaid":
            h = e.f["loan_terms_hash"]
            last[h] = max(last.get(h, ""), e.time)
    d_end = date.fromisoformat(end)
    by_year, rows, wsum, wtot = defaultdict(float), [], 0.0, 0.0
    for x in real.values():
        if x.status != "active":
            continue
        lr = max((last.get(h, "") for h in x.hashes), default="")
        since = (d_end - date.fromisoformat(lr[:10])).days if lr else None
        mat = (date.fromisoformat(x.originated[:10]) + timedelta(days=x.duration_days)).isoformat() if x.duration_days else None
        if mat:
            by_year[mat[:4]] += x.outstanding
            wsum += x.outstanding * (date.fromisoformat(mat) - d_end).days / 365.25
            wtot += x.outstanding
        rows.append({"root": x.root, "outstanding": x.outstanding, "maturity": mat, "last_payment": lr[:10],
                     "days_since_payment": since, "age_days": (d_end - date.fromisoformat(x.originated[:10])).days})
    terms = [x.duration_days for x in real.values() if x.duration_days and x.status == "active"]
    return {"active": len(rows), "term_days_min": min(terms, default=None), "term_days_max": max(terms, default=None),
            "outstanding_by_maturity_year": dict(sorted(by_year.items())),
            "weighted_years_to_maturity": (wsum / wtot) if wtot else None,
            "max_days_since_payment": max((r["days_since_payment"] for r in rows if r["days_since_payment"] is not None),
                                          default=None),
            "late_over_45d": [r["root"] for r in rows if r["days_since_payment"] and r["days_since_payment"] > 45],
            "never_paid_older_than_45d": [r["root"] for r in rows if r["days_since_payment"] is None and r["age_days"] > 45],
            "loans": rows}


def stress_scenarios(btab: list[dict], outstanding: float, recon: dict, escrow_open: float) -> dict:
    """Loss to vault assets and resulting NAV under simple default scenarios with a
    given recovery on the GPU collateral. Arithmetic on the reconciled state, not a
    credit model."""
    ta, sh = recon.get("total_assets") or 0.0, recon.get("total_shares") or 1.0
    bt = sorted(btab, key=lambda r: -r["outstanding"])
    exposures = {"largest borrower": bt[0]["outstanding"] if bt else 0.0,
                 "three largest borrowers": sum(r["outstanding"] for r in bt[:3]),
                 "every borrower": outstanding}
    rows = []
    for rec in (0.6, 0.4, 0.2):
        for who, exp in exposures.items():
            loss = exp * (1 - rec)
            rows.append({"who": who, "recovery": rec, "loss": loss, "loss_pct_assets": loss / ta if ta else None,
                         "nav_after": (ta - loss) / sh})
    worst = outstanding * 0.6 + escrow_open
    rows.append({"who": "every borrower, and the open escrow is not returned", "recovery": 0.4, "loss": worst,
                 "loss_pct_assets": worst / ta if ta else None, "nav_after": (ta - worst) / sh})
    return {"rows": rows, "top1_outstanding_share": (bt[0]["outstanding"] / outstanding) if bt and outstanding else None,
            "top3_outstanding_share": (sum(r["outstanding"] for r in bt[:3]) / outstanding) if outstanding else None,
            "idle_over_pending": (recon.get("deposit_balance") or 0) /
                                 max((recon.get("pending_redemption_shares") or 0) * (recon.get("redemption_share_price") or 1), 1)}


def implied_compute(book: dict, loans_csv_rows: dict, end: str, prices: tuple = (1.5, 2.0, 2.56, 3.0, 3.36, 4.0, 5.0),
                    utilization: float = 0.7, kw_per_gpu: float = 1.5) -> dict:
    """What the debt implies about the compute behind it. Annual debt service =
    interest on outstanding principal at each loan's rate + straight-line
    amortization over the remaining term. Divide by a rental price to get the
    GPU-hours per year the borrowers must sell, then GPUs at a utilization and
    power at a per-GPU draw (server share, before cooling). A bound, not a
    measurement: it ignores borrower opex and assumes rental revenue is the only
    source of repayment."""
    d_end = date.fromisoformat(end)
    interest = amort = 0.0
    for row in book["loans"]:
        ln = loans_csv_rows[row["root"]]
        yrs = max((date.fromisoformat(row["maturity"]) - d_end).days / 365.25, 0.25) if row["maturity"] else 2.6
        interest += ln.outstanding * (ln.rate_apr or 0.0)
        amort += ln.outstanding / yrs
    ds = interest + amort
    curve = []
    for p in prices:
        gh = ds / p
        gpus = gh / (8760 * utilization)
        curve.append({"price": p, "gpu_hours_per_year": gh, "gpus": round(gpus), "mw": gpus * kw_per_gpu / 1000})
    return {"annual_interest": interest, "annual_amortization": amort, "annual_debt_service": ds,
            "utilization": utilization, "kw_per_gpu": kw_per_gpu, "curve": curve}


def breakeven(ic: dict, pledged_gpus: int, utilization: float = 0.7) -> dict:
    """Rental price per GPU-hour at which the pledged fleet covers debt service."""
    hours = pledged_gpus * 8760 * utilization
    return {"pledged_gpus": pledged_gpus, "breakeven_price": (ic["annual_debt_service"] / hours) if hours else None,
            "price_full_utilization": (ic["annual_debt_service"] / (pledged_gpus * 8760)) if pledged_gpus else None,
            "mw_pledged": pledged_gpus * ic["kw_per_gpu"] / 1000}


def _verification(p: Path) -> dict | None:
    """Result of `compute_forensics verify` (GoldRush checked against public RPC), if it was run."""
    return json.loads(p.read_text()) if p.exists() else None


def _ratio_min(a: list[dict], b: list[dict]) -> dict | None:
    """USDai priced in PYUSD. Removes price-feed noise that hits both tokens on the same day."""
    pb = {r["date"]: r["price"] for r in b if r.get("price")}
    rs = [(r["price"] / pb[r["date"]], r["date"]) for r in a if r.get("price") and pb.get(r["date"])]
    if not rs:
        return None
    v, d = min(rs)
    return {"ratio": v, "date": d}


def _activity_stats(act: dict, borrowers: list[str]) -> dict:
    from statistics import median
    b = [len(act[a]) for a in borrowers if a in act]
    h = [len(v) for a, v in act.items() if a not in set(borrowers)]
    return {"borrowers": len(b), "borrower_chains_min": min(b, default=None), "borrower_chains_max": max(b, default=None),
            "borrower_chains_median": median(b) if b else None, "holders": len(h),
            "holder_chains_min": min(h, default=None), "holder_chains_max": max(h, default=None),
            "holder_chains_median": median(h) if h else None}


def run(frozen: Path, results: Path, paper: Path) -> dict:
    bad = verify(frozen)
    if bad:
        raise SystemExit(f"frozen data does not match MANIFEST.sha256: {bad}")
    proto = _load(frozen / "protocol_txs.json.gz")
    scans = _load(frozen / "hub_events.json.gz")
    hold = _load(frozen / "holders.json.gz")
    prices = _load(frozen / "prices.json.gz")
    accounts = _load(frozen / "accounts.json.gz")
    lp_raw = _load(frozen / "livepeer.json.gz")
    ak_raw = _load(frozen / "akash.json.gz")
    sol = _load(frozen / "solana.json.gz")
    extras = _load(frozen / "extras.json.gz")
    state = _load(frozen / "state.json.gz")
    trace = _load(frozen / "escrow_trace.json.gz")
    col_raw = _load(frozen / "collateral.json.gz") if (frozen / "collateral.json.gz").exists() else {}
    events = merge(from_protocol_txs(proto), from_scans(scans))

    # RQ1/RQ4: loan book
    loans, meta = L.build_loans(events)
    real = {k: v for k, v in loans.items() if not L.is_test_loan(v)}
    btab = L.borrower_table(loans)
    orig = sum(x.principal for x in real.values())
    outstanding = sum(x.outstanding for x in real.values())

    # RQ2: vault NAV, supply, accrued vs cash yield
    nav = V.nav_series(events)
    start, end = min(nav), max(nav)
    nav_d = V.fill_daily(nav, start, end)
    supply = V.supply_series(events)
    supply_d = V.fill_daily(supply, min(supply), end)
    accrued = V.yield_accrued(nav_d, supply_d)
    cash = V.cash_yield(events, meta["hash_ccy"])
    tot_accrued = sum(accrued.values())
    tot_cash = {k: sum(m.get(k, 0.0) for m in cash.values()) for k in ("loan_interest", "base_yield", "fees", "escrow_interest")}
    ann_total = V.annualized(nav_d, start, end)
    last90 = (date.fromisoformat(end) - timedelta(days=90)).isoformat()
    ann_90 = V.annualized(nav_d, last90, end) if last90 in nav_d else None
    usdai = V.usdai_flows(events)
    queue = V.redemption_queue(events)
    admin_fee = V.base_yield_admin_fees(events)
    base_src = V.base_yield_by_source(events)

    # RQ3/RQ6: holders
    conc, tops, venues = {}, {}, {}
    names, sums = accounts.get("names", {}), accounts.get("summaries", {})
    for ch, toks in hold.items():
        for sym, snap in toks.items():
            conc[f"{ch}:{sym}"] = H.concentration([int(r["balance"]) for r in snap["rows"]])
            tops[f"{ch}:{sym}"] = H.top_holders(snap, names, sums, ch)
            venues[f"{ch}:{sym}"] = H.venue_exposure(snap, names, ch)
    s_supply = H.supply_by_chain(hold, "sUSDai")
    u_supply = H.supply_by_chain(hold, "USDai")
    multi = H.cross_chain_addresses(hold, "sUSDai")
    vault_idle = next((int(r["balance"]) / 1e18 for r in hold[R.HUB]["USDai"]["rows"] if r["address"] == R.SUSDAI), 0.0)
    sol_shares = (sol.get("sUSDai") or {}).get("ui_amount", 0.0)
    total_shares = sum(s_supply.values()) + sol_shares
    claims = total_shares * nav_d[end]

    # RQ5: redemptions vs GPU rental prices
    gpu = _gpu_weekly(frozen.parent / "external")
    gw = dict(gpu)
    weeks = [w for w in queue["weekly_requests"] if w in gw]
    xs = [queue["weekly_requests"][w] for w in weeks]
    gpu_chg = []
    for w in weeks:
        prev = (date.fromisoformat(w) - timedelta(days=7)).isoformat()
        gpu_chg.append((gw[w] / gw[prev] - 1) if prev in gw else 0.0)
    rho_level = V.spearman(xs, [gw[w] for w in weeks])
    rho_change = V.spearman(xs, gpu_chg)

    funding = repayment_funding(events, meta, accounts)
    dests = principal_destinations(loans, accounts)

    # Part B: realized on-chain compute demand
    from . import market_analysis as MA
    from . import collateral as COL
    lp = MA.livepeer(lp_raw)
    ak = MA.akash(ak_raw, "2025-05-12", end)
    gd = [p for d, p in gpu if d <= (ak.get("retrieved_at") or "9999")[:10]]
    h100_central = gd[-1] if gd else None

    # Reconciliation against the vault's own accounting (eth_call snapshot)
    vs = state.get("vault", {})
    def _w(k, i=0):
        v = vs.get(k)
        return int(v[i]) / 1e18 if isinstance(v, list) else None
    recon = {"block": state.get("block"), "total_assets": _w("totalAssets"), "total_shares": _w("totalShares"),
             "hub_supply": _w("totalSupply"), "bridged_supply": _w("bridgedSupply"),
             "deposit_balance": _w("balances", 0), "serviced_redemption_balance": _w("balances", 1),
             "deposit_timelock_balance": _w("depositTimelockBalance"),
             "pending_loan_balance": _w("loanRouterBalances", 0), "accrued_loan_interest": _w("loanRouterBalances", 1),
             "base_yield_accrued": _w("claimableBaseYield"),
             "escrow_interest_accrued": (int(state["escrow_accrued"][0]) / 1e18) if state.get("escrow_accrued") else None,
             "deposit_share_price": _w("depositSharePrice"), "redemption_share_price": _w("redemptionSharePrice")}
    recon["pending_redemption_shares"] = (recon["total_shares"] or 0) - (recon["hub_supply"] or 0) - (recon["bridged_supply"] or 0)
    recon["loan_book_gap"] = outstanding - (recon["pending_loan_balance"] or 0)
    recon["shares_gap"] = (supply_d[end] + queue["pending_shares"]) - (recon["total_shares"] or 0)
    recon["spoke_plus_solana"] = sum(v for k, v in s_supply.items() if k != R.HUB) + sol_shares

    # Escrow pre-funding: vault escrow deposits that never became an on-chain loan
    loan_hashes = {h for x in loans.values() for h in x.hashes}
    esc = [e for e in events if e.name == "sUSDai.LoanEscrowTimelockDeposited"]
    closed = {e.f["loan_terms_hash"] for e in events
              if e.name in ("sUSDai.LoanEscrowTimelockWithdrawn", "sUSDai.LoanEscrowTimelockCancelled")}
    open_escrow = [{"time": e.time, "hash": e.f["loan_terms_hash"], "usd": e.f["usdai_amount"] / 1e18,
                    "apr": e.f["interest_rate"] * 31_536_000 / 1e18, "tx": e.tx}
                   for e in esc if e.f["loan_terms_hash"] not in loan_hashes | closed]
    from . import market_analysis as MA0
    flows = MA0.stable_flows(trace)
    escrow = {"deposits_total": sum(e.f["usdai_amount"] for e in esc) / 1e18, "n_deposits": len(esc),
              "n_closed": len(closed), "n_cancelled": sum(1 for e in events if e.name == "sUSDai.LoanEscrowTimelockCancelled"),
              "open": open_escrow, "flows": flows, "summaries": trace.get("summaries", {}),
              "balances": trace.get("balances", {}), "activity": trace.get("activity", {})}

    # Extras: cross-chain activity map and Ethereum holder history
    eth_hist = {}
    for d, snap in (extras.get("eth_susdai_holders_monthly") or {}).items():
        c = H.concentration([int(r["balance"]) for r in snap["rows"]])
        eth_hist[d] = {"block": snap["block"], "holders": c.get("holders", 0), "supply": c.get("total", 0.0),
                       "top1": c.get("top1", 0.0)}

    res = {
        # window starts at the vault deployment block date; nav_start is the first deposit
        "window": {"start": "2025-05-12", "nav_start": start, "end": end, "end_block": scans.get("end_block"),
                   "failed_windows": len(scans.get("failed_windows") or [])},
        "events_decoded": len(events),
        "loans": {"n_all": len(loans), "n": len(real), "n_test": len(loans) - len(real),
                  "originated": orig, "outstanding": outstanding,
                  "interest_paid": sum(x.interest_paid for x in real.values()),
                  "principal_repaid": sum(x.principal_repaid for x in real.values()),
                  "fees_paid": sum(x.fees_paid for x in real.values()),
                  "repaid": sum(1 for x in real.values() if x.status == "repaid"),
                  "breached": sum(1 for x in real.values() if x.status in ("breached", "liquidated")),
                  "migrated": sum(1 for x in real.values() if len(x.hashes) > 1),
                  "borrowers": len(btab), "hhi_originated": L.hhi([r["originated"] for r in btab]),
                  "hhi_outstanding": L.hhi([r["outstanding"] for r in btab if r["outstanding"] > 0]),
                  "top1_share": btab[0]["originated"] / orig if btab else None,
                  "top3_share": sum(r["originated"] for r in btab[:3]) / orig if btab else None,
                  "rate_min": min((x.rate_apr for x in real.values() if x.rate_apr), default=None),
                  "rate_max": max((x.rate_apr for x in real.values() if x.rate_apr), default=None),
                  "rate_wavg_outstanding": (sum(x.rate_apr * x.outstanding for x in real.values() if x.rate_apr) /
                                            max(sum(x.outstanding for x in real.values() if x.rate_apr), 1)),
                  "susdai_funded_share": (sum(x.current_principal * (x.susdai_share or 0) for x in real.values()
                                              if x.susdai_share is not None) /
                                          max(sum(x.current_principal for x in real.values()
                                                  if x.susdai_share is not None), 1)),
                  "lender_interest": meta["lender_interest"], "fees_by_kind": meta["fees_by_kind"],
                  "reserve_accounts": len(meta["reserve_accounts"])},
        "vault": {"nav_start": nav_d[start], "nav_end": nav_d[end], "ann_total": ann_total, "ann_90d": ann_90,
                  "shares_from_events": supply_d[end], "shares_from_holders": total_shares,
                  "claims_usd": claims, "idle_usdai": vault_idle, "loan_book": outstanding,
                  "unexplained_assets": claims - vault_idle - outstanding,
                  "accrued_total": tot_accrued, "cash": tot_cash, "admin_fee": admin_fee, "base_yield_sources": base_src,
                  "cash_coverage": (sum(tot_cash.values()) / tot_accrued) if tot_accrued else None,
                  "cash_coverage_borrowers_only": ((tot_cash["loan_interest"] + tot_cash["fees"]) / tot_accrued)
                  if tot_accrued else None},
        "usdai": {"by_token": usdai["by_token"],
                  "minted": sum(v["mint_usd"] for v in usdai["by_token"].values()),
                  "burned": sum(v["burn_usd"] for v in usdai["by_token"].values()),
                  "supply_by_chain": u_supply},
        "queue": {k: v for k, v in queue.items() if k not in ("weekly_requests", "batches")},
        "queue_batches": queue["batches"],
        "gpu": {"weeks_overlap": len(weeks), "spearman_level": rho_level, "spearman_change": rho_change,
                "h100_first": gpu[0] if gpu else None, "h100_last": gpu[-1] if gpu else None},
        "holders": {"concentration": conc, "top": tops, "venues": venues, "susdai_supply_by_chain": s_supply,
                    "cross_chain": multi},
        "repayment_funding": funding, "principal_destinations": dests,
        "book_health": loan_book_health(real, events, end),
        "stress": stress_scenarios(btab, outstanding, recon, sum(x["usd"] for x in open_escrow)),
        "implied_compute": implied_compute(loan_book_health(real, events, end), real, end),
        "collateral": COL.analyze(col_raw, loans, L.is_test_loan) if col_raw else {},
        "breakeven": breakeven(implied_compute(loan_book_health(real, events, end), real, end),
                               (COL.analyze(col_raw, loans, L.is_test_loan) if col_raw else {}).get("active_gpus", 0)),
        "solana": sol, "reconciliation": recon, "escrow": escrow,
        "livepeer": {k: v for k, v in lp.items() if k not in ("gateway_values", "orchestrator_values")},
        "akash": {k: v for k, v in ak.items() if k != "active_gpu_series"},
        "h100_central_last": h100_central,
        "eth_holder_history": eth_hist,
        "verification": _verification(frozen.parent / "verification" / "onchain_checks.json"),
        "activity": extras.get("activity") or {},
        "activity_stats": _activity_stats(extras.get("activity") or {}, [r["borrower"] for r in btab]),
        "usdai_pyusd_ratio_min": _ratio_min(prices.get("USDai") or [], prices.get("PYUSD") or []),
        "prices": {k: {"min": min((r["price"] for r in v), default=None),
                       "max": max((r["price"] for r in v), default=None),
                       "last": v[-1] if v else None} for k, v in prices.items()},
    }
    results.mkdir(parents=True, exist_ok=True)
    (results / "results.json").write_text(json.dumps(res, indent=1, default=str, sort_keys=True))
    _csv(results / "loans.csv", [{
        "root_hash": x.root, "version": x.version, "originated": x.originated, "borrower": x.borrower,
        "currency": L.SYMBOL.get(x.currency, x.currency), "principal": round(x.principal, 2),
        "current_principal": round(x.current_principal, 2), "outstanding": round(x.outstanding, 2),
        "interest_paid": round(x.interest_paid, 2), "payments": x.payments, "status": x.status,
        "rate_apr": None if x.rate_apr is None else round(x.rate_apr, 4), "duration_days": x.duration_days,
        "collateral_items": x.collateral_items, "terms_hashes": len(x.hashes), "origin_tx": x.origin_tx,
        "test_loan": L.is_test_loan(x)} for x in sorted(loans.values(), key=lambda v: v.originated)])
    _csv(results / "borrowers.csv", [{**r, "statuses": "|".join(r["statuses"])} for r in btab])
    _csv(results / "monthly_yield.csv", [{"month": m, "accrued_usd": round(accrued.get(m, 0.0), 2),
                                          **{k: round(cash.get(m, {}).get(k, 0.0), 2)
                                             for k in ("loan_interest", "base_yield", "fees", "escrow_interest")}}
                                         for m in sorted(set(accrued) | set(cash))])
    _csv(results / "nav_daily.csv", [{"date": d, "nav": round(v, 8), "shares": round(supply_d.get(d, 0.0), 2)}
                                     for d, v in nav_d.items()])

    figdir = paper / "figures"
    figures.originations(list(loans.values()), figdir)
    figures.nav_and_peg(nav_d, prices, figdir)
    figures.yield_sources(accrued, cash, figdir)
    names_ = {"arbitrum": "Arbitrum", "eth": "Ethereum", "base": "Base", "plasma": "Plasma"}
    figures.holder_concentration({names_.get(k.split("-")[0], k): v for k, v in conc.items()
                                  if k.endswith(":sUSDai")}, figdir)
    figures.redemptions_vs_gpu(queue["weekly_requests"], nav_d, gpu, figdir)
    figures.supply_chains({**{k.split("-")[0]: v for k, v in s_supply.items()}, "solana": sol_shares}, figdir)
    figures.queue_timeline(queue["batches"], queue["weekly_requests"], nav_d, figdir)
    usdai_cash = {m: sum(v.values()) for m, v in cash.items()}
    orig_m = defaultdict(float)
    for x in real.values():
        orig_m[x.originated[:7]] += x.principal
    figures.markets_monthly({
        "USD.AI loan originations": dict(orig_m),
        "USD.AI cash yield to vault": usdai_cash,
        "Akash network spend": ak["monthly_usd"],
        "Livepeer ticket payments": {m: v["usd"] for m, v in lp["monthly"].items()},
    }, figdir)
    figures.akash_gpu(ak["active_gpu_series"], ak["monthly_usd"], figdir)
    price_rows = []
    if h100_central:
        price_rows.append(("H100, centralized clouds (GetDeploying median)", h100_central))
    for key, lab in (("h100-80Gi", "H100 80GB, Akash median"), ("a100-80Gi", "A100 80GB, Akash median")):
        if key in ak["models"]:
            price_rows.append((lab, ak["models"][key]["price_med"]))
    figures.gpu_prices(price_rows, figdir)
    if res["collateral"]:
        figures.collateral_ltv([r for r in res["collateral"]["per_loan"] if r["status"] == "active" and r["collateral_value"]],
                               figdir)
    ic = res["implied_compute"]
    figures.implied_gpus([(c["price"], c["gpus"]) for c in ic["curve"]], ak.get("gpu_total_now"), figdir)
    figures.lorenz_named({"Livepeer gateways": lp["gateway_values"], "Livepeer orchestrators": lp["orchestrator_values"],
                          "USD.AI borrowers": [r["originated"] for r in btab]}, figdir, "fig_lorenz_markets")
    roles = {r["borrower"]: "borrower" for r in btab}
    for key, rows in tops.items():
        for t in rows[:6]:
            roles.setdefault(t["address"], "holder")
    figures.activity_heatmap({a: c for a, c in (extras.get("activity") or {}).items() if a in roles}, roles, figdir)
    figures.eth_holders(eth_hist, figdir)
    if recon.get("total_assets"):
        px = recon["redemption_share_price"] or 1.0
        figures.balance_sheet(
            [("Deposit balance\n(idle USDai)", recon["deposit_balance"] or 0),
             ("Escrow pre-funding", recon["deposit_timelock_balance"] or 0),
             ("Active loans", recon["pending_loan_balance"] or 0),
             ("Accrued interest\n+ base yield", (recon["accrued_loan_interest"] or 0) + (recon["base_yield_accrued"] or 0)
              + (recon["escrow_interest_accrued"] or 0))],
            [("Arbitrum", (recon["hub_supply"] or 0) * px),
             ("Bridged out", (recon["bridged_supply"] or 0) * px),
             ("Pending redemptions", (recon["pending_redemption_shares"] or 0) * px)], figdir)
    fl = flows
    def _sum(src, dst, kind=None):
        return sum(v for sym, b, v in fl.get(src, {}).get("out", []) if b == dst and (kind is None or kind in sym))
    ESC, HUBW = "0x844bb7b6223f6af028189bb34d6341a5733d6286", "0x11687ca5235d669e8d52d7946b1605826cf521b1"
    OFF, SVC = "0xf845a0a05cbd91ac15c3e59d126de5dfbc2aabb7", "0x264bd8291fae1d75db2c5f573b07faa6715997b5"
    BOR = "0x64447901dc34bd610ac562b2c612784a9954d39d"
    vault_to_esc = sum(v for sym, b, v in fl.get(ESC, {}).get("in", []) if b == R.SUSDAI)
    hub_in = {b: v for sym, b, v in fl.get(HUBW, {}).get("in", [])}
    edges = [("sUSDai vault", "Escrow facility\n(Safe)", vault_to_esc, "USDai"),
             ("Escrow facility\n(Safe)", "PYUSD hub", _sum(ESC, HUBW), "PYUSD"),
             ("Borrower 1", "PYUSD hub", hub_in.get(BOR, 0.0), "PYUSD"),
             ("PYUSD hub", "Off-ramp A\n(19 chains)", _sum(HUBW, OFF), "PYUSD"),
             ("PYUSD hub", "Service wallet B", _sum(HUBW, SVC), "PYUSD"),
             ("Fee recipient", "Off-ramp A\n(19 chains)", sum(v for sym, b, v in fl.get("0x728f9bfcc9a40144464656770d2c08492e903c28", {}).get("out", []) if b == OFF), "PYUSD")]
    edges = [e for e in edges if e[2] > 0]
    if edges:
        figures.flow_graph({"sUSDai vault": (0.04, 0.62), "Escrow facility\n(Safe)": (0.30, 0.62),
                            "PYUSD hub": (0.60, 0.62), "Off-ramp A\n(19 chains)": (0.95, 0.62),
                            "Borrower 1": (0.30, 0.12), "Service wallet B": (0.95, 0.12),
                            "Fee recipient": (0.95, 1.02)}, edges, figdir)
    figures.at_a_glance([
        (f"${orig / 1e6:,.0f}M", "GPU loans originated"),
        (f"${outstanding / 1e6:,.0f}M", "loans outstanding"),
        (f"{len(btab)}", "borrowers"),
        (f"{100 * (btab[0]['originated'] / orig):.0f}%", "largest borrower share"),
        (f"{100 * (ann_total or 0):.1f}%", "annualized NAV growth"),
        (f"{100 * (sum(tot_cash.values()) / tot_accrued if tot_accrued else 0):.0f}%",
         "of NAV yield received in cash"),
        (f"{queue['wait_days_median']:.0f} days", "median redemption wait"),
        (f"{total_shares / 1e6:,.0f}M", "sUSDai shares on 5 chains"),
        (f"{100 * (recon.get('deposit_timelock_balance') or 0) / (recon.get('total_assets') or 1):.0f}%",
         "of vault assets: escrow, no loan"),
        (f"{orig / max(ak['usd_window'] + lp['usd_total'], 1):.0f}x", "GPU credit vs Akash+Livepeer spend"),
    ], figdir)

    from .paper import write_generated
    write_generated(res, loans, btab, paper / "generated")
    from .visuals import build as build_visuals
    build_visuals(results, figdir, paper.parent / "visuals")
    log.info("analysis complete: %d events, %d loans", len(events), len(real))
    return res
