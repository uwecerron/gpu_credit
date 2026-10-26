"""Part B analysis: realized on-chain compute demand (Livepeer, Akash) and how it
compares with GPU credit (USD.AI) and centralized rental prices."""
from __future__ import annotations

from collections import defaultdict

from .holders import concentration
from .loans import hhi
from .markets import LP_EVENTS

_LP = {e.topic: e for e in LP_EVENTS}


def _decode_lp(lg: dict):
    ev = _LP.get((lg.get("tp") or [None])[0])
    if not ev:
        return None
    from eth_abi import decode
    try:
        idx = [decode([t], bytes.fromhex(x[2:]))[0] for t, x in zip(ev.indexed, lg["tp"][1:])]
        dat = decode(list(ev.data), bytes.fromhex((lg["d"] or "0x")[2:]))
    except Exception:
        return None
    return ev.name, dict(zip(ev.fields, [v.lower() if isinstance(v, str) else v for v in idx + list(dat)]))


def livepeer(lp: dict) -> dict:
    """Payments for transcoding/AI inference: WinningTicketTransfer amounts are the
    ETH actually moved from a gateway's deposit to an orchestrator."""
    eth = {r["date"]: r["price"] for r in lp.get("eth_usd") or []}
    last_px = None
    monthly = defaultdict(lambda: {"eth": 0.0, "usd": 0.0, "tickets": 0})
    by_sender, by_recipient = defaultdict(float), defaultdict(float)
    face = 0.0
    for lg in lp["events"].get("LP.WinningTicketTransfer", []):
        d = _decode_lp(lg)
        if not d:
            continue
        f = d[1]
        amt = f["amount"] / 1e18
        day = lg["t"][:10]
        px = eth.get(day) or last_px
        last_px = px or last_px
        m = monthly[day[:7]]
        m["eth"] += amt
        m["usd"] += amt * (px or 0.0)
        m["tickets"] += 1
        by_sender[f["sender"]] += amt * (px or 0.0)
        by_recipient[f["recipient"]] += amt * (px or 0.0)
    for lg in lp["events"].get("LP.WinningTicketRedeemed", []):
        d = _decode_lp(lg)
        if d:
            face += d[1]["face_value"] / 1e18
    tot = sum(v["usd"] for v in monthly.values())
    top_g = sorted(by_sender.items(), key=lambda kv: -kv[1])
    return {"monthly": dict(sorted(monthly.items())), "usd_total": tot,
            "eth_total": sum(v["eth"] for v in monthly.values()), "face_value_eth": face,
            "tickets": sum(v["tickets"] for v in monthly.values()),
            "gateways": len(by_sender), "orchestrators": len(by_recipient),
            "hhi_gateways": hhi(list(by_sender.values())), "hhi_orchestrators": hhi(list(by_recipient.values())),
            "top_gateway_share": (top_g[0][1] / tot) if tot and top_g else None,
            "top3_gateway_share": (sum(v for _, v in top_g[:3]) / tot) if tot else None,
            "gateway_values": [v for _, v in top_g],
            "orchestrator_values": sorted(by_recipient.values(), reverse=True),
            "failed_windows": len(lp.get("failed") or [])}


def akash(ak: dict, start: str = "2025-05-12", end: str = "2026-10-21") -> dict:
    """start/end are ISO dates; spend inside the window is summed by day, not by month."""
    monthly = defaultdict(float)
    window_usd = 0.0
    for r in ak.get("dailyUUsdSpent", []):
        monthly[r["date"][:7]] += r["value"] / 1e6
        if start <= r["date"][:10] <= end:
            window_usd += r["value"] / 1e6
    gpus = {r["date"][:10]: r["value"] for r in ak.get("activeGPU", [])}
    models = {f"{m['model']}-{m['ram']}": {"price_med": m["price"]["med"], "price_wavg": m["price"]["weightedAverage"],
                                           "total": m["availability"]["total"],
                                           "available": m["availability"]["available"]}
              for m in ak.get("gpu-prices", {}).get("models", []) if m.get("price")}   # unpriced models skipped
    in_window = [v for k, v in gpus.items() if start <= k <= end]
    cap = ak["network-capacity"]["resources"]["gpu"]
    return {"monthly_usd": dict(sorted(monthly.items())), "usd_window": window_usd,
            "usd_all_time": ak["dashboard-data"]["now"]["totalUUsdSpent"] / 1e6,
            "active_gpu_series": dict(sorted(gpus.items())),
            "active_gpu_min": min(in_window) if in_window else None,
            "active_gpu_max": max(in_window) if in_window else None,
            "active_gpu_now": cap["active"],          # live network-capacity snapshot
            "gpu_total_now": cap["total"],
            "providers_now": ak["network-capacity"]["activeProviderCount"],
            "models": models, "retrieved_at": ak.get("retrieved_at")}


def lorenz_inputs(values: list[float]) -> dict:
    return concentration([int(v * 1e6) for v in values if v > 0])


def stable_flows(trace: dict) -> dict:
    """Per traced address: stablecoin inflows/outflows by counterparty (USD),
    plus USDai redemptions paid out as PYUSD."""
    from . import registry as R
    from .abi import decode_log
    stable = {R.USDAI: ("USDai", 18), R.PYUSD_ARB: ("PYUSD", 6), R.USDC_ARB: ("USDC", 6)}
    zero = "0x" + "0" * 40
    out = {}
    for a, txs in (trace.get("txs") or {}).items():
        ins, outs = defaultdict(float), defaultdict(float)
        for t in txs:
            for lg in t["logs"]:
                d = decode_log(lg["tp"], lg["d"], only={"ERC20.Transfer", "USDai.Withdrawn"})
                if not d:
                    continue
                name, f = d
                if name == "USDai.Withdrawn":
                    if f["caller"] == a:
                        outs[("PYUSD via USDai redemption", f["recipient"])] += f["withdraw_amount"] / 1e6
                    continue
                if lg["a"] not in stable:
                    continue
                sym, dec = stable[lg["a"]]
                v = f["value"] / 10 ** dec
                if f["to"] == a:
                    ins[(sym, f["from"])] += v
                elif f["from"] == a and f["to"] != zero:
                    outs[(sym, f["to"])] += v
        out[a] = {"in": sorted(((k[0], k[1], v) for k, v in ins.items()), key=lambda x: -x[2]),
                  "out": sorted(((k[0], k[1], v) for k, v in outs.items()), key=lambda x: -x[2])}
    return out
