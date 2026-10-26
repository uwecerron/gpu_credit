"""Holder concentration and venue exposure (RQ3) and cross-chain footprint (RQ6)."""
from __future__ import annotations

import re

from . import registry as R

VENUE_PATTERNS = [
    ("Pendle", r"\bpendle\b|\bSY[- ]|\bPT[- ]|\bYT[- ]"),
    ("Morpho", r"morpho|metamorpho"),
    ("Aave", r"\baave\b|^a(arb|eth|bas|pla)\w*usdai"),
    ("Euler", r"euler|\be[A-Za-z]+usdai"),
    ("Fluid", r"\bfluid\b|\bf[A-Z]\w*"),
    ("Silo", r"\bsilo\b"),
    ("Curve", r"curve|crv"),
    ("Balancer", r"balancer|\bbpt\b"),
    ("Uniswap", r"uniswap|\buni-v"),
    ("Dolomite", r"dolomite"),
    ("Gearbox", r"gearbox|\bd[A-Z]"),
    ("LayerZero/OFT", r"\boft\b|layerzero|oadapter"),
    ("Vault/strategy", r"vault|boring|mellow|veda|strategy|\bsavings\b"),
]


def classify_name(names: list[str]) -> str:
    text = " | ".join(names)
    for label, pat in VENUE_PATTERNS:
        if re.search(pat, text, re.I):
            return label
    return "unlabeled"


def concentration(balances: list[int]) -> dict:
    b = sorted((x for x in balances if x > 0), reverse=True)
    tot = sum(b)
    if not tot:
        return {"holders": 0}
    shares = [x / tot for x in b]
    n = len(b)
    asc = sorted(b)
    gini = (2 * sum((i + 1) * x for i, x in enumerate(asc)) / (n * tot)) - (n + 1) / n
    return {"holders": n, "total": tot / 1e18, "top1": shares[0], "top5": sum(shares[:5]),
            "top10": sum(shares[:10]), "hhi": sum(s * s for s in shares), "gini": gini}


def top_holders(snapshot: dict, names: dict, summaries: dict, chain: str, n: int = 10) -> list[dict]:
    rows = sorted(snapshot["rows"], key=lambda r: -int(r["balance"]))
    tot = sum(int(r["balance"]) for r in rows) or 1
    out = []
    for r in rows[:n]:
        key = f"{chain}:{r['address']}"
        nm = names.get(key, [])
        label = "sUSDai vault" if r["address"] == R.SUSDAI else classify_name(nm)
        s = summaries.get(key, {})
        out.append({"address": r["address"], "balance": int(r["balance"]) / 1e18, "share": int(r["balance"]) / tot,
                    "names": nm[:3], "label": label, "txs": s.get("total"), "first_seen": s.get("first")})
    return out


def venue_exposure(snapshot: dict, names: dict, chain: str) -> dict[str, float]:
    tot = sum(int(r["balance"]) for r in snapshot["rows"]) or 1
    out: dict[str, float] = {}
    for r in snapshot["rows"]:
        key = f"{chain}:{r['address']}"
        if key not in names:
            continue
        lab = classify_name(names[key])
        if lab != "unlabeled":
            out[lab] = out.get(lab, 0.0) + int(r["balance"]) / tot
    return out


def supply_by_chain(holders: dict, token: str) -> dict[str, float]:
    return {ch: sum(int(r["balance"]) for r in toks[token]["rows"]) / 1e18
            for ch, toks in holders.items() if token in toks}


def cross_chain_addresses(holders: dict, token: str, min_balance: float = 1e5) -> dict[str, list[str]]:
    """Addresses holding >= min_balance on more than one chain (CREATE2 deployments)."""
    seen: dict[str, list[str]] = {}
    for ch, toks in holders.items():
        for r in toks.get(token, {}).get("rows", []):
            if int(r["balance"]) / 1e18 >= min_balance:
                seen.setdefault(r["address"], []).append(ch)
    return {a: chs for a, chs in seen.items() if len(chs) > 1}
