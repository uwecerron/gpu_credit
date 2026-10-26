"""Collectors. Each stage is resumable (API responses for closed block windows and
complete pages are cached) and writes one gzip JSON file under data/raw/.
Run `python -m compute_forensics collect --stage all`."""
from __future__ import annotations

import gzip
import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path

from . import goldrush as G
from . import registry as R
from .abi import BY_NAME, decode_log
from .client import ApiError

log = logging.getLogger("compute_forensics")

# (event name, emitting contract) pairs scanned across the whole hub history.
HUB_SCANS = [
    ("USDai.Deposited", R.USDAI), ("USDai.Withdrawn", R.USDAI), ("USDai.Harvested", R.USDAI),
    ("sUSDai.Deposit", R.SUSDAI), ("sUSDai.Withdraw", R.SUSDAI),
    ("sUSDai.RedeemRequest", R.SUSDAI), ("sUSDai.RedemptionProcessed", R.SUSDAI),
    ("sUSDai.RedemptionsServiced", R.SUSDAI), ("sUSDai.BaseYieldDeposited", R.SUSDAI),
    ("sUSDai.LoanTimelockDeposited", R.SUSDAI), ("sUSDai.LoanTimelockCancelled", R.SUSDAI),
    ("sUSDai.LoanDepositTimelockDeposited", R.SUSDAI), ("sUSDai.LoanDepositTimelockCancelled", R.SUSDAI),
    ("sUSDai.LoanEscrowTimelockDeposited", R.SUSDAI), ("sUSDai.LoanEscrowTimelockWithdrawn", R.SUSDAI),
]


def _dump(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with gzip.open(tmp, "wt", encoding="utf-8") as fh:
        json.dump(obj, fh, sort_keys=True)
    tmp.replace(path)


def load(path: Path, default=None):
    try:
        with gzip.open(path, "rt", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return default


def stage_protocol(api, raw: Path) -> None:
    out = {}
    for name, addr in R.PROTOCOL_CONTRACTS.items():
        out[name] = [G.slim_tx(t) for t in G.iter_transactions(api, R.HUB, addr)]
        log.info("protocol %s: %d txs", name, len(out[name]))
    _dump(raw / "protocol_txs.json.gz", out)


def stage_scan(api, raw: Path, workers: int = 6) -> None:
    end_block = G.block_at(api, R.HUB, date.today().isoformat())
    wins = G.windows(R.GENESIS_BLOCK, end_block)
    jobs = [(ev, sender, lo, hi) for ev, sender in HUB_SCANS for lo, hi in wins]
    log.info("scan: %d events x %d windows = %d calls (end block %d)", len(HUB_SCANS), len(wins), len(jobs), end_block)
    results: dict[str, list] = {ev: [] for ev, _ in HUB_SCANS}
    failed = []

    def run(job):
        ev, sender, lo, hi = job
        return job, G.events_by_topic(api, R.HUB, BY_NAME[ev].topic, sender, lo, hi, final=hi < end_block - 50_000)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = [pool.submit(run, j) for j in jobs]
        for n, f in enumerate(as_completed(futs), 1):
            try:
                (ev, _s, _lo, _hi), logs = f.result()
                results[ev] += logs
            except ApiError as e:
                failed.append(str(e)[:200])
            if n % 200 == 0:
                log.info("scan progress %d/%d", n, len(jobs))
    for ev in results:  # de-duplicate and order
        uniq = {(x["h"], x["i"]): x for x in results[ev]}
        results[ev] = sorted(uniq.values(), key=lambda x: (x["b"] or 0, x["i"] or 0))
        log.info("scan %s: %d logs", ev, len(results[ev]))
    _dump(raw / "hub_events.json.gz", {"end_block": end_block, "events": results, "failed_windows": failed})
    if failed:
        log.warning("%d windows failed; rerun `collect --stage scan` (cached windows are free)", len(failed))


def stage_holders(api, raw: Path) -> None:
    out = {}
    for chain in (R.HUB,) + R.SPOKES:
        out[chain] = {}
        for sym, token in (("sUSDai", R.SUSDAI), ("USDai", R.USDAI)):
            try:
                rows, block = G.holders(api, chain, token)
            except ApiError as e:
                log.warning("holders %s %s: %s", chain, sym, e)
                continue
            out[chain][sym] = {"block": block, "rows": rows}
            log.info("holders %s %s: %d", chain, sym, len(rows))
    _dump(raw / "holders.json.gz", out)


def stage_prices(api, raw: Path) -> None:
    out = {}
    for sym, token in (("sUSDai", R.SUSDAI), ("USDai", R.USDAI), ("PYUSD", R.PYUSD_ARB)):
        out[sym] = G.daily_prices(api, R.HUB, token, "2025-05-12", R.STUDY_END_DATE)
        log.info("prices %s: %d days", sym, len(out[sym]))
    _dump(raw / "prices.json.gz", out)


def _loan_parties(raw: Path) -> tuple[set, set]:
    """Borrowers and lenders from decoded loan events."""
    from .abi import decode_loan_terms_v2
    data = load(raw / "protocol_txs.json.gz", {}) or {}
    borrowers, lenders = set(), set()
    for txs in data.values():
        for t in txs:
            for lg in t["logs"]:
                d = decode_log(lg["tp"], lg["d"])
                if not d:
                    continue
                name, f = d
                if name == "LR1.LoanOriginated":
                    borrowers.add(f["borrower"])
                elif name == "LR2.LoanOriginated":
                    borrowers.add(decode_loan_terms_v2(f["loan_terms"])["borrower"])
                elif name in ("LR.LenderPositionMinted", "LR.LenderRepaid"):
                    lenders.add(f["lender"])
    return borrowers, lenders


def stage_accounts(api, raw: Path, top_n: int = 25, borrower_pages: int = 40) -> None:
    """Summaries for top holders, borrowers and lenders; full history for borrowers
    (to follow principal out and repayment funding in)."""
    borrowers, lenders = _loan_parties(raw)
    hold = load(raw / "holders.json.gz", {}) or {}
    targets = {(R.HUB, a) for a in borrowers | lenders}
    for chain, toks in hold.items():
        for sym, snap in toks.items():
            top = sorted(snap["rows"], key=lambda r: -int(r["balance"]))[:top_n]
            targets |= {(chain, r["address"]) for r in top}
    out = {"summaries": {}, "names": {}, "borrower_txs": {}}
    log.info("accounts: %d targets, %d borrowers", len(targets), len(borrowers))
    for n, (chain, addr) in enumerate(sorted(targets), 1):
        key = f"{chain}:{addr}"
        if n % 25 == 0:
            log.info("accounts progress %d/%d", n, len(targets))
        try:
            s = G.summary(api, chain, addr, cache=True) or {}
            out["summaries"][key] = {"total": s.get("total_count"),
                                     "first": (s.get("earliest_transaction") or {}).get("block_signed_at"),
                                     "last": (s.get("latest_transaction") or {}).get("block_signed_at")}
            first = api.get(f"/v1/{chain}/address/{addr}/transactions_v3/page/0/", {}, cache_when=G._has_next)
            names = {(lg.get("sender_name"), lg.get("sender_contract_ticker_symbol"))
                     for t in first.get("items") or [] for lg in t.get("log_events") or []
                     if (lg.get("sender_address") or "").lower() == addr}
            out["names"][key] = sorted({n for pair in names for n in pair if n})
        except ApiError as e:
            log.warning("account %s: %s", key, e)
    for addr in sorted(borrowers):
        try:
            txs = []
            for t in G.iter_transactions(api, R.HUB, addr, max_pages=borrower_pages):
                txs.append(G.slim_tx(t))
            out["borrower_txs"][addr] = txs
            log.info("borrower %s: %d txs", addr, len(txs))
        except ApiError as e:
            out["borrower_txs"][addr] = None
            log.warning("borrower %s: %s", addr, e)
    _dump(raw / "accounts.json.gz", out)


def _livepeer(api, raw):
    from .markets import stage_livepeer
    stage_livepeer(api, raw)


def _akash(api, raw):
    from .markets import stage_akash
    stage_akash(raw)


def _solana(api, raw):
    from .markets import stage_solana
    stage_solana(raw)


def _state(api, raw):
    from .markets import stage_state
    stage_state(raw)


def _escrow(api, raw):
    from .markets import stage_escrow_trace
    stage_escrow_trace(api, raw)


def _extras(api, raw):
    from .markets import stage_extras
    stage_extras(api, raw, raw / "accounts.json.gz")


def stage_boundaries(api, raw: Path, workers: int = 6) -> None:
    """Patch for data collected before events_by_topic asked for hi + 1: GoldRush's
    `ending-block` is exclusive, so the last block of every scan window was skipped.
    Fetch exactly those blocks for every scanned event and merge them in."""
    from .markets import LIVEPEER_TICKET_BROKER, LP_EVENTS

    def patch(path: Path, specs: list[tuple[str, str, str]]):
        d = load(path)
        ends = [hi for _, hi in G.windows(R.GENESIS_BLOCK, d["end_block"])]
        jobs = [(name, topic, sender, b) for name, topic, sender in specs for b in ends]

        def run(j):
            name, topic, sender, b = j
            return name, G.events_by_topic(api, R.HUB, topic, sender, b, b, final=True)
        added = 0
        with ThreadPoolExecutor(max_workers=workers) as pool:
            for f in as_completed([pool.submit(run, j) for j in jobs]):
                name, logs = f.result()
                cur = d["events"].setdefault(name, [])
                have = {(x["h"], x["i"]) for x in cur}
                new = [x for x in logs if (x["h"], x["i"]) not in have]
                cur += new
                added += len(new)
        for k in d["events"]:
            d["events"][k].sort(key=lambda x: (x["b"] or 0, x["i"] or 0))
        d["boundary_patch"] = {"blocks_checked": len(ends), "logs_added": added}
        _dump(path, d)
        log.info("boundaries %s: %d blocks x %d events, %d logs added", path.name, len(ends), len(specs), added)

    patch(raw / "hub_events.json.gz", [(ev, BY_NAME[ev].topic, sender) for ev, sender in HUB_SCANS])
    patch(raw / "livepeer.json.gz", [(ev.name, ev.topic, LIVEPEER_TICKET_BROKER) for ev in LP_EVENTS])


def _collateral(api, raw):
    """Hardware-token metadata behind each loan (tokenURI by eth_call, record from the
    protocol's metadata host). Needs the protocol and scan stages."""
    from .collateral import fetch
    from .events import from_protocol_txs, from_scans, merge
    proto, scans = load(raw / "protocol_txs.json.gz"), load(raw / "hub_events.json.gz")
    fetch(proto, merge(from_protocol_txs(proto), from_scans(scans)), raw)


STAGES = {"protocol": stage_protocol, "scan": stage_scan, "holders": stage_holders,
          "prices": stage_prices, "accounts": stage_accounts, "livepeer": _livepeer,
          "akash": _akash, "solana": _solana, "state": _state, "escrow": _escrow, "extras": _extras, "boundaries": stage_boundaries,
          "collateral": _collateral}
