"""Collateral behind the loans. The BundleCollateralWrapper wraps ERC-721 tokens
from the USD.AI Tokenized Hardware contract (USDAI-TH). Each token's on-chain
tokenURI points to a metadata record naming the server, its collateral value,
useful life, depreciation start and serial number. We read the token IDs from the
wrapper's transfer logs (GoldRush), the URIs from the contract (eth_call) and the
records from the metadata host, and map each token to the loan it secures."""
from __future__ import annotations

import gzip
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import requests
from eth_abi import decode

from . import registry as R

log = logging.getLogger(__name__)
HARDWARE_NFT = "0xb31f04f920f24eda3ad276d55c5afefad6230c5d"   # "USD.AI Tokenized Hardware", from name()
TRANSFER = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
ARB_RPC = "https://arb1.arbitrum.io/rpc"


def wrapped_tokens(protocol_txs: dict) -> list[dict]:
    """Every hardware token moved into the wrapper, with the tx and the wrapper token
    minted in the same transaction (the bundle id the loan references)."""
    out = []
    for t in protocol_txs.get("BundleCollateralWrapper", []):
        bundle = None
        for lg in t["logs"]:
            if lg["a"] == R.BUNDLE_COLLATERAL_WRAPPER and lg["tp"][0] == TRANSFER and len(lg["tp"]) == 4 \
                    and lg["tp"][1].endswith("0" * 40):
                bundle = int(lg["tp"][3], 16)
        for lg in t["logs"]:
            if lg["a"] == HARDWARE_NFT and lg["tp"][0] == TRANSFER and len(lg["tp"]) == 4 \
                    and lg["tp"][2].endswith(R.BUNDLE_COLLATERAL_WRAPPER[2:]):
                out.append({"token_id": int(lg["tp"][3], 16), "tx": t["h"], "time": t["t"], "bundle_id": bundle,
                            "from": "0x" + lg["tp"][1][-40:]})
    return out


def loan_term_token_ids(events) -> dict[str, list[int]]:
    """collateral_token_ids from every decoded LoanTermsV2, keyed by terms hash."""
    from .abi import decode_loan_terms_v2
    out = {}
    for e in events:
        if e.name in ("LR2.LoanOriginated", "LR2.LoanMigrated", "LR2.LoanRefinanced", "LR2.LoanRefinanced3"):
            t = decode_loan_terms_v2(e.f.get("loan_terms") or e.f.get("new_loan_terms"))
            h = e.f.get("loan_terms_hash") or e.f.get("new_loan_terms_hash")
            if t.get("collateral_token", "").lower() == HARDWARE_NFT:
                out[h] = [int(x) for x in t.get("collateral_token_ids") or []]
    return out


def fetch(protocol_txs: dict, events, raw: Path, ca: str | bool = True, probe: range = range(1000, 1040)) -> dict:
    """Token IDs come from the wrapper's transfer logs and from every LoanTermsV2;
    `probe` also tries a range of IDs so hardware tokens prepared but not yet pledged
    are seen. For each ID: tokenURI and ownerOf by eth_call, then the metadata record."""
    toks = wrapped_tokens(protocol_txs)
    by_hash = loan_term_token_ids(events)
    ids = {t["token_id"] for t in toks} | {i for v in by_hash.values() for i in v} | set(probe)
    sess = requests.Session()

    def call(data: str):
        r = sess.post(ARB_RPC, json={"jsonrpc": "2.0", "id": 1, "method": "eth_call",
                                     "params": [{"to": HARDWARE_NFT, "data": data}, "latest"]}, timeout=60,
                      verify=ca).json()
        return r.get("result")

    recs = {}
    for tid in sorted(ids):
        word = hex(tid)[2:].rjust(64, "0")
        uri_raw = call("0xc87b56dd" + word)
        uri = decode(["string"], bytes.fromhex(uri_raw[2:]))[0] if uri_raw and len(uri_raw) > 2 else None
        own = call("0x6352211e" + word)
        owner = ("0x" + own[-40:]) if own and len(own) > 2 else None
        rec = {"token_id": tid, "token_uri": uri, "owner": owner, "metadata": None}
        if uri:
            try:
                m = sess.get(uri, timeout=60, verify=ca)
                rec["metadata"] = m.json() if m.ok else {"http_status": m.status_code}
            except (requests.RequestException, ValueError) as e:
                rec["metadata"] = {"error": str(e)[:200]}
        if uri or owner or tid in {t["token_id"] for t in toks}:
            recs[tid] = rec
    log.info("collateral: %d token ids, %d with metadata, %d minted", len(recs),
             sum(1 for x in recs.values() if x["metadata"] and "name" in x["metadata"]),
             sum(1 for x in recs.values() if x["owner"]))
    out = {"retrieved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "nft": HARDWARE_NFT,
           "rpc": ARB_RPC, "wrapped": toks, "by_terms_hash": by_hash, "records": {str(k): v for k, v in recs.items()}}
    with gzip.open(raw / "collateral.json.gz", "wt") as f:
        json.dump(out, f)
    return out


def _attr(meta: dict, name: str):
    for a in meta.get("attributes", []):
        if a.get("trait_type") == name:
            return a.get("value")
    return None


GPUS_PER_UNIT = {"GB200": 72, "H200": 8, "B200": 8, "B300": 8, "H100": 8}


def _model(name: str) -> str:
    import re
    g = re.search(r"(GB200|H200|H100|B300|B200|A100|RTX PRO 6000|RTX 6000|RTX 5090|L40S?)", name or "", re.I)
    if g:
        return g.group(1).upper().replace("PRO 6000", "6000")
    return "other"


def _record_row(tid: int, rec: dict) -> dict | None:
    m = rec.get("metadata") or {}
    if "name" not in m:
        return None
    model = _model(m.get("name"))
    qty = int(_attr(m, "Quantity") or 1)
    per = GPUS_PER_UNIT.get(model)
    ds = _attr(m, "Depreciation Start")
    return {"token_id": tid, "name": m.get("name"), "model": model, "units": qty,
            "gpus": qty * per if per else None, "value_usd": float(_attr(m, "Collateral Value USD") or 0),
            "useful_life_days": _attr(m, "Useful Life (days)"),
            "depreciation_start": (datetime.fromtimestamp(int(ds), tz=timezone.utc).date().isoformat()
                                   if str(ds).isdigit() else ds),
            "manufacturer": _attr(m, "Manufacturer"), "serial": _attr(m, "Serial Number"),
            "owner": rec.get("owner")}


def analyze(col: dict, loans: dict, is_test) -> dict:
    """Per-loan collateral (stated value, units, GPUs, LTV) and what is minted but not pledged."""
    recs = {int(k): v for k, v in col.get("records", {}).items()}
    rows = {tid: r for tid, r in ((tid, _record_row(tid, rec)) for tid, rec in recs.items()) if r}
    by_hash = {h: v for h, v in col.get("by_terms_hash", {}).items()}
    # bundle id -> hardware tokens wrapped into it (V1 loans reference the bundle)
    bundle_tokens: dict[int, list[int]] = {}
    for t in col.get("wrapped", []):
        if t.get("bundle_id") is not None:
            bundle_tokens.setdefault(t["bundle_id"], []).append(t["token_id"])
    per_loan, pledged = [], set()
    for x in loans.values():
        if is_test(x):
            continue
        ids = []
        for h in reversed(x.hashes):
            if h in by_hash:
                ids = by_hash[h]
                break
        hw = []
        for i in ids:
            hw += bundle_tokens.get(i, [i])        # a bundle id expands to its wrapped hardware tokens
        items = [rows[i] for i in hw if i in rows]
        if x.status == "active":
            pledged.update(i for i in hw if i in rows)
        val = sum(r["value_usd"] for r in items)
        gp = sum(r["gpus"] or 0 for r in items)
        per_loan.append({"root": x.root, "borrower": x.borrower, "status": x.status, "outstanding": x.outstanding,
                         "principal": x.principal, "collateral_value": val, "ltv": (x.outstanding / val) if val else None,
                         "ltv_at_origination": (x.principal / val) if val else None,
                         "units": sum(r["units"] for r in items), "gpus": gp,
                         "models": sorted({r["model"] for r in items}), "n_items": len(items)})
    active = [r for r in per_loan if r["status"] == "active" and r["collateral_value"]]
    act_val = sum(r["collateral_value"] for r in active)
    act_out = sum(r["outstanding"] for r in active)
    unpledged = [r for tid, r in rows.items() if tid not in pledged and r["value_usd"] >= 1e6]
    for u in unpledged:          # which loan, if any, it secured before
        prior = [r for r in per_loan if r["status"] != "active" and u["token_id"] in
                 {i for h in loans[r["root"]].hashes for i in by_hash.get(h, [])}]
        u["previously_secured"] = ({"root": prior[-1]["root"], "principal": prior[-1]["principal"],
                                    "borrower": prior[-1]["borrower"]} if prior else None)
    return {"per_loan": per_loan, "active_collateral_value": act_val, "active_outstanding_with_collateral": act_out,
            "book_ltv": (act_out / act_val) if act_val else None,
            "active_gpus": sum(r["gpus"] for r in active), "active_units": sum(r["units"] for r in active),
            "ltv_min": min((r["ltv"] for r in active), default=None), "ltv_max": max((r["ltv"] for r in active), default=None),
            "models_active": sorted({m for r in active for m in r["models"]}),
            "useful_life_days": sorted({r["useful_life_days"] for r in rows.values() if r["useful_life_days"]}),
            "unpledged": sorted(unpledged, key=lambda r: -r["value_usd"]),
            "unpledged_value": sum(r["value_usd"] for r in unpledged),
            "n_records": len(rows), "retrieved_at": col.get("retrieved_at")}
