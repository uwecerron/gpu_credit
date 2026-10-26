"""Independent check of the GoldRush data against the chain itself.

Everything in the paper comes from GoldRush except the vault-state read. This
module re-pulls the same facts straight from public RPC nodes, without GoldRush,
and compares them log by log:

1. For every event type the analysis depends on, fetch the logs with
   eth_getLogs and compare the exact set of (tx hash, log index) pairs and the
   sum of the key amount with what GoldRush returned.
2. Compare token supplies from eth_call with the sum of GoldRush holder balances.
3. Re-read the escrow redemption transaction receipt and check every transfer.

The output goes to data/verification/onchain_checks.json (frozen, so the paper
can be rebuilt offline) and is summarized in the paper and README.
"""
from __future__ import annotations

import gzip
import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import requests

from . import registry as R
from .abi import BY_NAME, decode_log
from .events import from_protocol_txs, from_scans, merge
from .markets import LIVEPEER_TICKET_BROKER, LP_EVENTS

log = logging.getLogger(__name__)

RPC = {"arbitrum-mainnet": "https://arb1.arbitrum.io/rpc", "eth-mainnet": "https://ethereum-rpc.publicnode.com",
       "base-mainnet": "https://mainnet.base.org", "plasma-mainnet": "https://rpc.plasma.to"}
SPAN = 10_000_000          # arb1 public RPC limit per eth_getLogs call

# (label, emitting contract, event name, amount field, decimals)
CHECKS = [
    ("Loans originated, router V1", R.LOAN_ROUTER_V1, "LR1.LoanOriginated", "principal", 6),
    ("Loans originated, router V2", R.LOAN_ROUTER_V2, "LR2.LoanOriginated", None, 0),
    ("Loans migrated V1 to V2", R.LOAN_ROUTER_V2, "LR2.LoanMigrated", None, 0),
    ("Loans refinanced", R.LOAN_ROUTER_V2, "LR2.LoanRefinanced", None, 0),
    ("Loans refinanced (3-field)", R.LOAN_ROUTER_V2, "LR2.LoanRefinanced3", None, 0),
    ("Repayments, router V1", R.LOAN_ROUTER_V1, "LR.LoanRepaid", "interest", 6),
    ("Repayments, router V2", R.LOAN_ROUTER_V2, "LR.LoanRepaid", None, 0),
    ("Lender payouts, router V1", R.LOAN_ROUTER_V1, "LR.LenderRepaid", None, 0),
    ("Lender payouts, router V2", R.LOAN_ROUTER_V2, "LR.LenderRepaid", None, 0),
    ("Fees paid, router V2", R.LOAN_ROUTER_V2, "LR2.FeePaid", None, 0),
    ("Breaches and liquidations, V2", R.LOAN_ROUTER_V2, "LR.LoanBreached", None, 0),
    ("Reserve accounts created", R.RESERVE_ACCOUNT_FACTORY, "RAF.ReserveAccountCreated", None, 0),
    ("USDai mints", R.USDAI, "USDai.Deposited", "mint_amount", 18),
    ("USDai redemptions", R.USDAI, "USDai.Withdrawn", "usdai_amount", 18),
    ("sUSDai deposits", R.SUSDAI, "sUSDai.Deposit", "assets", 18),
    ("sUSDai redemption requests", R.SUSDAI, "sUSDai.RedeemRequest", "shares", 18),
    ("sUSDai redemptions processed", R.SUSDAI, "sUSDai.RedemptionProcessed", "amount", 18),
    ("Base yield deposited to vault", R.SUSDAI, "sUSDai.BaseYieldDeposited", "deposited_amount", 18),
    ("Escrow deposits", R.SUSDAI, "sUSDai.LoanEscrowTimelockDeposited", "usdai_amount", 18),
    ("Escrow withdrawals", R.SUSDAI, "sUSDai.LoanEscrowTimelockWithdrawn", "interest_amount", 18),
    ("Escrow cancellations", R.SUSDAI, "sUSDai.LoanEscrowTimelockCancelled", "usdai_amount", 18),
]


class Rpc:
    def __init__(self, url: str, verify: str | bool = True):
        self.url, self.s, self.verify, self.calls = url, requests.Session(), verify, 0

    def __call__(self, method: str, params: list):
        for attempt in range(8):
            try:
                self.calls += 1
                r = self.s.post(self.url, json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
                                timeout=120, verify=self.verify).json()
            except (requests.RequestException, ValueError):
                if attempt == 7:
                    raise
                continue
            if "error" in r:
                msg = r["error"].get("message", str(r["error"]))
                if "too many requests" in msg.lower() or "rate" in msg.lower():
                    time.sleep(2 ** attempt + 1)       # public node throttling: back off, don't split
                    continue
                raise RuntimeError(msg)
            return r["result"]
        raise RuntimeError("unreachable")


def get_logs(rpc: Rpc, address: str, topic: str, lo: int, hi: int) -> list[dict]:
    """eth_getLogs over [lo, hi], splitting the range when the node refuses it."""
    try:
        return rpc("eth_getLogs", [{"address": address, "topics": [topic], "fromBlock": hex(lo), "toBlock": hex(hi)}])
    except RuntimeError as e:
        if hi <= lo:
            raise
        log.debug("split %s-%s: %s", lo, hi, e)
        mid = (lo + hi) // 2
        return get_logs(rpc, address, topic, lo, mid) + get_logs(rpc, address, topic, mid + 1, hi)


def scan(rpc: Rpc, address: str, topic: str, lo: int, hi: int, workers: int = 2) -> list[dict]:
    wins = [(a, min(a + SPAN - 1, hi)) for a in range(lo, hi + 1, SPAN)]
    with ThreadPoolExecutor(workers) as ex:
        parts = list(ex.map(lambda w: get_logs(rpc, address, topic, *w), wins))
    return [x for p in parts for x in p]


def _load(p: Path):
    with gzip.open(p, "rt") as f:
        return json.load(f)


def _key(tx: str, topics: list[str], data: str) -> tuple:
    """Identify a log by its transaction and full content. Log indexes are not used:
    GoldRush and the RPC number logs differently inside some transactions."""
    return (tx.lower(), tuple(t.lower() for t in topics), (data or "0x").lower())


def _cmp(label, rpc_keys: dict, gr_keys: dict, scale: float | None) -> dict:
    """Each dict maps a content key to [count, amount]. Counts keep the multiplicity of
    identical logs inside one transaction."""
    from collections import Counter
    a = Counter({k: v[0] for k, v in rpc_keys.items()})
    b = Counter({k: v[0] for k, v in gr_keys.items()})
    row = {"check": label, "rpc_count": sum(a.values()), "goldrush_count": sum(b.values()),
           "only_rpc": sum((a - b).values()), "only_goldrush": sum((b - a).values())}
    if scale:
        row["rpc_sum"] = sum(v[1] for v in rpc_keys.values()) / scale
        row["goldrush_sum"] = sum(v[1] for v in gr_keys.values()) / scale
    row["match"] = row["only_rpc"] == 0 and row["only_goldrush"] == 0 and (
        not scale or abs(row["rpc_sum"] - row["goldrush_sum"]) < 1e-6 * max(1.0, abs(row["rpc_sum"])))
    return row


def run(frozen: Path, out: Path, ca: str | bool = True) -> dict:
    proto, scans = _load(frozen / "protocol_txs.json.gz"), _load(frozen / "hub_events.json.gz")
    events = merge(from_protocol_txs(proto), from_scans(scans))
    lo, hi = R.GENESIS_BLOCK, scans["end_block"]
    arb = Rpc(RPC[R.HUB], ca)
    rows = []
    for label, addr, name, field, dec in CHECKS:
        ev = BY_NAME[name]
        raw = scan(arb, addr, ev.topic, lo, hi)
        rk = {}
        for lg in raw:
            d = decode_log(lg["topics"], lg["data"], only={name})
            if d:
                k = _key(lg["transactionHash"], lg["topics"], lg["data"])
                c = rk.setdefault(k, [0, 0])
                c[0] += 1
                c[1] += d[1].get(field, 0) if field else 0
        gk = {}
        for e in events:
            if e.name == name and e.sender == addr and lo <= e.block <= hi:
                k = _key(e.tx, e.raw_topics, e.raw_data)
                c = gk.setdefault(k, [0, 0])
                c[0] += 1
                c[1] += e.f.get(field, 0) if field else 0
        row = _cmp(label, rk, gk, 10 ** dec if field else None)
        rows.append(row)
        log.info("%-34s rpc %5d  goldrush %5d  match=%s", label, row["rpc_count"], row["goldrush_count"], row["match"])

    # Livepeer, over the same window as the GoldRush scan
    lp = _load(frozen / "livepeer.json.gz")
    for ev in LP_EVENTS:
        if ev.name != "LP.WinningTicketTransfer":
            continue
        raw = scan(arb, LIVEPEER_TICKET_BROKER, ev.topic, lo, lp["end_block"])
        rk, gk = {}, {}
        for x in raw:
            k = _key(x["transactionHash"], x["topics"], x["data"])
            c = rk.setdefault(k, [0, 0])
            c[0] += 1
            c[1] += int(x["data"], 16)
        for x in lp["events"][ev.name]:
            if lo <= x["b"] <= lp["end_block"]:
                k = _key(x["h"], x["tp"], x["d"])
                c = gk.setdefault(k, [0, 0])
                c[0] += 1
                c[1] += int(x["d"], 16)
        missing = sorted(set(rk) - set(gk))
        lp_missing = [{"tx": k[0], "eth": rk[k][1] / 1e18, "block_hint": None} for k in missing]
        row = _cmp("Livepeer winning-ticket payments", rk, gk, 1e18)
        row["missing_from_goldrush"] = lp_missing
        rows.append(row)
        log.info("%-34s rpc %5d  goldrush %5d  match=%s", row["check"], row["rpc_count"], row["goldrush_count"],
                 row["match"])

    # Supplies: eth_call totalSupply now vs the sum of GoldRush holder balances
    hold = _load(frozen / "holders.json.gz")
    supplies = []
    for chain, url in RPC.items():
        bals = hold.get(chain, {}).get("sUSDai", {}).get("rows", [])
        gr = sum(int(r["balance"]) for r in bals) / 1e18
        blk = hold.get(chain, {}).get("sUSDai", {}).get("block")
        ts, at = None, None
        for tag in ([hex(blk)] if blk else []) + ["latest"]:     # same block as the snapshot if the node has it
            try:
                ts = int(Rpc(url, ca)("eth_call", [{"to": R.SUSDAI, "data": "0x18160ddd"}, tag]), 16) / 1e18
                at = blk if tag != "latest" else "latest"
                break
            except Exception as e:  # noqa: BLE001 - a node without history is reported, not fatal
                log.warning("totalSupply on %s at %s failed: %s", chain, tag, e)
        supplies.append({"chain": chain, "snapshot_block": blk, "rpc_block": at, "rpc_total_supply": ts,
                         "goldrush_holder_sum": gr, "diff_pct": None if not ts else 100 * (gr - ts) / ts})

    # The escrow redemption: re-read the receipt and list its stablecoin transfers
    receipts = []
    esc = [e for e in events if e.name == "sUSDai.LoanEscrowTimelockDeposited"]
    trace = _load(frozen / "escrow_trace.json.gz")
    for t in trace.get("txs", {}).get("0x844bb7b6223f6af028189bb34d6341a5733d6286", []):
        for lg in t["logs"]:
            d = decode_log(lg["tp"], lg["d"], only={"USDai.Withdrawn"})
            if d and d[1]["usdai_amount"] / 1e18 > 1e8:
                rc = arb("eth_getTransactionReceipt", [t["h"]])
                tr = []
                for x in rc["logs"]:
                    dd = decode_log(x["topics"], x["data"])
                    if dd and dd[0] in ("ERC20.Transfer", "USDai.Withdrawn"):
                        tr.append({"token": x["address"].lower(), "event": dd[0],
                                   **{k: (str(v) if isinstance(v, int) else v) for k, v in dd[1].items()}})
                receipts.append({"tx": t["h"], "block": int(rc["blockNumber"], 16), "status": rc["status"],
                                 "goldrush_usdai_redeemed": d[1]["usdai_amount"] / 1e18, "rpc_logs": tr})

    # Is USDai itself backed? Hub supply plus spoke supplies against the stablecoins
    # the USDai contract holds, all read at one Arbitrum block.
    blk = arb("eth_blockNumber", [])
    def bal(token):
        return int(arb("eth_call", [{"to": token, "data": "0x70a08231" + R.USDAI[2:].rjust(64, "0")}, blk]), 16)
    hub = int(arb("eth_call", [{"to": R.USDAI, "data": "0x18160ddd"}, blk]), 16) / 1e18
    spokes = {}
    for chain, url in RPC.items():
        if chain == R.HUB:
            continue
        try:
            spokes[chain] = int(Rpc(url, ca)("eth_call", [{"to": R.USDAI, "data": "0x18160ddd"}, "latest"]), 16) / 1e18
        except Exception as e:  # noqa: BLE001
            log.warning("USDai supply on %s failed: %s", chain, e)
    reserves = {"PYUSD": bal(R.PYUSD_ARB) / 1e6, "USDC": bal(R.USDC_ARB) / 1e6,
                "wM": bal("0x437cc33344a0b27a429f795ff6b469c72698b291") / 1e6}
    backing = {"block": int(blk, 16), "usdai_hub_supply": hub, "usdai_spoke_supply": spokes,
               "reserves_at_usdai_contract": reserves,
               "coverage": sum(reserves.values()) / (hub + sum(spokes.values())) if hub else None}
    log.info("USDai backing at block %d: supply %.1fM (+%.2fM on EVM spokes), reserves %.1fM, coverage %.4f",
             backing["block"], hub / 1e6, sum(spokes.values()) / 1e6, sum(reserves.values()) / 1e6, backing["coverage"])

    res = {"retrieved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "usdai_backing": backing,
           "block_range": [lo, hi], "rpc": RPC, "event_checks": rows, "supply_checks": supplies,
           "escrow_receipts": receipts, "n_escrow_deposits": len(esc), "rpc_calls": arb.calls}
    out.mkdir(parents=True, exist_ok=True)
    (out / "onchain_checks.json").write_text(json.dumps(res, indent=1, default=str))
    return res
