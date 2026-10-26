"""Decentralized compute markets (Part B): Livepeer on Arbitrum via GoldRush, and
Akash via its public Console API (Akash is a Cosmos chain that GoldRush does not
index). Plus two GoldRush "extras": cross-chain activity maps for key addresses
and historical holder snapshots on Ethereum.
"""
from __future__ import annotations

import gzip
import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timezone
from pathlib import Path

import requests

from . import goldrush as G
from . import registry as R
from .abi import Event
from .client import ApiError

log = logging.getLogger("compute_forensics")

LIVEPEER_TICKET_BROKER = "0xa8bb618b1520e284046f3dfc448851a1ff26e41b"   # Arbitrum, livepeer/protocol deployments
WETH_ARB = "0x82af49447d8a07e3bd95bd0d56f35241523fbab1"
AKASH_API = "https://console-api.akash.network/v1"
AKASH_SERIES = ["dailyUUsdSpent", "activeGPU", "activeLeaseCount", "dailyLeaseCount"]

LP_EVENTS = [
    Event("LP.WinningTicketRedeemed",
          "WinningTicketRedeemed(address,address,uint256,uint256,uint256,uint256,bytes)",
          ("address", "address"), ("uint256", "uint256", "uint256", "uint256", "bytes"),
          ("sender", "recipient", "face_value", "win_prob", "sender_nonce", "recipient_rand", "aux_data")),
    Event("LP.WinningTicketTransfer", "WinningTicketTransfer(address,address,uint256)",
          ("address", "address"), ("uint256",), ("sender", "recipient", "amount")),
]


def _dump(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with gzip.open(tmp, "wt", encoding="utf-8") as fh:
        json.dump(obj, fh, sort_keys=True)
    tmp.replace(path)


def stage_livepeer(api, raw: Path, workers: int = 6) -> None:
    end_block = G.block_at(api, R.HUB, date.today().isoformat())
    wins = G.windows(R.GENESIS_BLOCK, end_block)
    jobs = [(ev, lo, hi) for ev in LP_EVENTS for lo, hi in wins]
    out = {ev.name: [] for ev in LP_EVENTS}
    failed = []

    def run(job):
        ev, lo, hi = job
        return ev.name, G.events_by_topic(api, R.HUB, ev.topic, LIVEPEER_TICKET_BROKER, lo, hi,
                                          final=hi < end_block - 50_000)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for f in as_completed([pool.submit(run, j) for j in jobs]):
            try:
                name, logs = f.result()
                out[name] += logs
            except ApiError as e:
                failed.append(str(e)[:200])
    for k in out:
        out[k] = sorted({(x["h"], x["i"]): x for x in out[k]}.values(), key=lambda x: (x["b"] or 0, x["i"] or 0))
        log.info("livepeer %s: %d", k, len(out[k]))
    eth = G.daily_prices(api, R.HUB, WETH_ARB, "2025-05-12", R.STUDY_END_DATE)
    _dump(raw / "livepeer.json.gz", {"end_block": end_block, "events": out, "eth_usd": eth, "failed": failed})


def stage_akash(raw: Path) -> None:
    sess = requests.Session()
    out = {"retrieved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "source": AKASH_API}
    for name in AKASH_SERIES:
        r = sess.get(f"{AKASH_API}/graph-data/{name}", timeout=60)
        r.raise_for_status()
        out[name] = r.json().get("snapshots", [])
        log.info("akash %s: %d points", name, len(out[name]))
    for name in ("dashboard-data", "gpu-prices", "network-capacity"):
        r = sess.get(f"{AKASH_API}/{name}", timeout=60)
        r.raise_for_status()
        out[name] = r.json()
    _dump(raw / "akash.json.gz", out)


SOLANA_RPC = "https://api.mainnet-beta.solana.com"
SOLANA_MINTS = {"USDai": "USDai5XCUzNebYzUk6EuRiFCvnyoyEdj7VSyijYcz2A",     # docs.usd.ai contract addresses
                "sUSDai": "sUSDai6Y3GxysDEtA9BVcEFTaog6UZpYUVxJiMhAKYE"}


def stage_solana(raw: Path) -> None:
    """GoldRush does not serve Solana token supply, so read it from the public
    Solana RPC (getTokenSupply) to complete the cross-chain share count."""
    out = {"retrieved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "rpc": SOLANA_RPC}
    for sym, mint in SOLANA_MINTS.items():
        r = requests.post(SOLANA_RPC, json={"jsonrpc": "2.0", "id": 1, "method": "getTokenSupply", "params": [mint]},
                          timeout=30)
        r.raise_for_status()
        v = r.json()["result"]
        out[sym] = {"mint": mint, "slot": v["context"]["slot"], "ui_amount": float(v["value"]["uiAmountString"])}
        log.info("solana %s supply: %s", sym, out[sym]["ui_amount"])
    _dump(raw / "solana.json.gz", out)


def stage_extras(api, raw: Path, accounts_path: Path) -> None:
    """Cross-chain activity for borrowers and top holders, and monthly historical
    holder snapshots of sUSDai on Ethereum (historical holders are available on
    GoldRush 'Foundational' chains)."""
    from .collect import _loan_parties, load
    borrowers, _lenders = _loan_parties(raw)
    hold = load(raw / "holders.json.gz", {}) or {}
    targets = set(borrowers)
    for toks in hold.values():
        for snap in toks.values():
            targets |= {r["address"] for r in sorted(snap["rows"], key=lambda r: -int(r["balance"]))[:8]}
    targets = sorted(targets)
    activity = {}
    for a in targets:
        try:
            items = api.get(f"/v1/address/{a}/activity/", {}).get("items") or []
            activity[a] = sorted({(it.get("extends") or it).get("name") for it in items} - {None})
        except ApiError as e:
            log.warning("activity %s: %s", a, e)
    log.info("activity maps: %d addresses", len(activity))
    snaps = {}
    d = date(2025, 6, 1)
    while d <= date.today():
        try:
            blk = G.block_at(api, "eth-mainnet", d.isoformat())
            rows = []
            for page in range(50):
                data = api.get(f"/v1/eth-mainnet/tokens/{R.SUSDAI}/token_holders_v2/",
                               {"block-height": blk, "page-number": page})
                rows += [{"address": it["address"].lower(), "balance": str(it["balance"])}
                         for it in data.get("items") or []]
                if not (data.get("pagination") or {}).get("has_more"):
                    break
            snaps[d.isoformat()] = {"block": blk, "rows": rows}
            log.info("eth holders %s: %d", d, len(rows))
        except ApiError as e:
            log.warning("eth holders %s: %s", d, e)
        d = date(d.year + (d.month == 12), d.month % 12 + 1, 1)
    _dump(raw / "extras.json.gz", {"activity": activity, "eth_susdai_holders_monthly": snaps})


ARB_RPC = "https://arb1.arbitrum.io/rpc"
# sUSDai view functions (StakedUSDai.sol, BasePositionManager.sol, LoanRouterPositionManager.sol)
VAULT_VIEWS = {
    "nav": ("nav()", ["uint256"]), "totalAssets": ("totalAssets()", ["uint256"]),
    "totalShares": ("totalShares()", ["uint256"]), "totalSupply": ("totalSupply()", ["uint256"]),
    "bridgedSupply": ("bridgedSupply()", ["uint256"]), "balances": ("balances()", ["uint256", "uint256"]),
    "depositSharePrice": ("depositSharePrice()", ["uint256"]),
    "redemptionSharePrice": ("redemptionSharePrice()", ["uint256"]),
    "claimableBaseYield": ("claimableBaseYield()", ["uint256"]),
    "loanRouterBalances": ("loanRouterBalances()", ["uint256", "uint256"]),
    "depositTimelockBalance": ("depositTimelockBalance()", ["uint256"]),
}


def stage_state(raw: Path) -> None:
    """Point-in-time read of the vault's own accounting via eth_call (public
    Arbitrum RPC). This lets the reconstruction be reconciled against what the
    contract itself reports."""
    from eth_abi import decode as abi_decode
    from .abi import topic0
    sess = requests.Session()

    def call(to: str, sig: str, types: list[str], block: str):
        data = topic0(sig)[:10]
        r = sess.post(ARB_RPC, json={"jsonrpc": "2.0", "id": 1, "method": "eth_call",
                                     "params": [{"to": to, "data": data}, block]}, timeout=30)
        r.raise_for_status()
        res = r.json()
        if "error" in res:
            return {"error": res["error"].get("message")}
        return [str(x) for x in abi_decode(types, bytes.fromhex(res["result"][2:]))]

    blk = sess.post(ARB_RPC, json={"jsonrpc": "2.0", "id": 1, "method": "eth_blockNumber", "params": []},
                    timeout=30).json()["result"]
    out = {"retrieved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "rpc": ARB_RPC,
           "block": int(blk, 16), "vault": {}, "escrow_accrued": None}
    for name, (sig, types) in VAULT_VIEWS.items():
        out["vault"][name] = call(R.SUSDAI, sig, types, blk)
    out["escrow_accrued"] = call(R.ESCROW_TIMELOCK, "accrued()", ["uint256"], blk)
    out["usdai_base_yield_accrued"] = call(R.USDAI, "baseYieldAccrued()", ["uint256"], blk)
    # Is USDai itself backed? Hub supply (bridged-out tokens are burned on the hub, so
    # add the spokes) against the stablecoins the USDai contract holds.
    def bal(token: str) -> list[str]:
        data = topic0("balanceOf(address)")[:10] + R.USDAI[2:].rjust(64, "0")
        r = sess.post(ARB_RPC, json={"jsonrpc": "2.0", "id": 1, "method": "eth_call",
                                     "params": [{"to": token, "data": data}, blk]}, timeout=30).json()
        return [str(int(r["result"], 16))] if "result" in r else {"error": r.get("error")}
    out["usdai_supply"] = call(R.USDAI, "totalSupply()", ["uint256"], blk)
    out["usdai_reserves"] = {"PYUSD": bal(R.PYUSD_ARB), "USDC": bal(R.USDC_ARB),
                             "wM": bal("0x437cc33344a0b27a429f795ff6b469c72698b291")}
    log.info("vault state at block %d: %s", out["block"], {k: v for k, v in out["vault"].items()})
    _dump(raw / "state.json.gz", out)


ESCROW_FACILITY = "0x844bb7b6223f6af028189bb34d6341a5733d6286"   # receives the vault's escrow USDai (observed)


def stage_escrow_trace(api, raw: Path, max_hops: int = 2, min_usd: float = 1e6) -> None:
    """Follow USDai the vault sent to escrow: escrow facility -> USDai redemption
    -> PYUSD recipients, up to `max_hops`, keeping counterparties above min_usd."""
    from .abi import decode_log
    stable = {R.USDAI: 18, R.PYUSD_ARB: 6, R.USDC_ARB: 6}
    seen, frontier, out = set(), [ESCROW_FACILITY], {"txs": {}, "summaries": {}, "activity": {}, "balances": {}}
    for hop in range(max_hops + 1):
        nxt = []
        for a in frontier:
            if a in seen:
                continue
            seen.add(a)
            s = G.summary(api, R.HUB, a, cache=True) or {}
            out["summaries"][a] = {"total": s.get("total_count"),
                                   "first": (s.get("earliest_transaction") or {}).get("block_signed_at"),
                                   "last": (s.get("latest_transaction") or {}).get("block_signed_at")}
            items = api.get(f"/v1/address/{a}/activity/", {}).get("items") or []
            out["activity"][a] = sorted({(it.get("extends") or it).get("name") for it in items} - {None})
            bal = api.get(f"/v1/{R.HUB}/address/{a}/balances_v2/", {"no-spam": "true"}, cache=False).get("items") or []
            out["balances"][a] = {b.get("contract_ticker_symbol"): b.get("quote") for b in bal if (b.get("quote") or 0) > 1}
            if (s.get("total_count") or 0) > 1500:      # service-scale wallet: record, do not expand
                continue
            txs = [G.slim_tx(t) for t in G.iter_transactions(api, R.HUB, a, max_pages=20)]
            out["txs"][a] = txs
            agg = {}
            for t in txs:
                for lg in t["logs"]:
                    d = decode_log(lg["tp"], lg["d"], only={"ERC20.Transfer"})
                    if not d or lg["a"] not in stable:
                        continue
                    f = d[1]
                    if f["from"] == a and f["to"] != "0x" + "0" * 40:
                        agg[f["to"]] = agg.get(f["to"], 0.0) + f["value"] / 10 ** stable[lg["a"]]
            for t in txs:      # USDai redemptions pay PYUSD to the `recipient` field of USDai.Withdrawn
                for lg in t["logs"]:
                    d = decode_log(lg["tp"], lg["d"], only={"USDai.Withdrawn"})
                    if d and d[1]["caller"] == a:
                        agg[d[1]["recipient"]] = agg.get(d[1]["recipient"], 0.0) + d[1]["withdraw_amount"] / 1e6
            nxt += [b for b, v in agg.items() if v >= min_usd and b not in R.PROTOCOL_ADDRESSES]
        frontier = nxt
        log.info("escrow trace hop %d: %d addresses", hop, len(frontier))
    _dump(raw / "escrow_trace.json.gz", out)
