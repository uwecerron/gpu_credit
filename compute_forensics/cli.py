"""Command line. `collect` needs an API key; everything else runs offline from
data/frozen so anyone can reproduce the paper without paying for API calls."""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from .client import ApiError, GoldRushClient, ResponseCache
from .config import MissingKeyError, load_api_key
from .secrets_scan import scan

log = logging.getLogger("compute_forensics")
ROOT = Path(__file__).resolve().parent.parent
OK, LEAK, MISSING_KEY, API_ERROR = 0, 1, 3, 4


def cmd_collect(a) -> int:
    from . import collect
    api = GoldRushClient(load_api_key([Path.cwd(), ROOT]), cache=ResponseCache(a.data / "cache"))
    stages = list(collect.STAGES) if a.stage == "all" else [a.stage]
    for s in stages:
        log.info("stage %s", s)
        collect.STAGES[s](api, a.data / "raw")
    log.info("API calls made: %d", api.calls)
    return OK


def cmd_freeze(a) -> int:
    from .freeze import freeze
    freeze(a.data / "raw", a.data / "frozen")
    return OK


def cmd_analyze(a) -> int:
    from .pipeline import run
    run(a.data / "frozen", ROOT / "results", ROOT / "paper")
    return OK


def cmd_verify(a) -> int:
    from .verify import run
    res = run(a.data / "frozen", a.data / "verification")
    bad = [r["check"] for r in res["event_checks"] if not r["match"]]
    if bad:
        log.error("mismatch between GoldRush and the chain: %s", ", ".join(bad))
        return 1
    log.info("all %d event checks match the chain", len(res["event_checks"]))
    return OK


def cmd_scan(a) -> int:
    try:
        extra = load_api_key([Path.cwd(), ROOT]).reveal()
    except MissingKeyError:
        extra = None
    hits = scan(ROOT, extra)
    if hits:
        log.error("KEY FOUND in: %s", ", ".join(hits))
        return LEAK
    log.info("ok: no API keys found outside .env")
    return OK


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="compute_forensics", description=__doc__)
    p.add_argument("--data", type=Path, default=ROOT / "data")
    p.add_argument("--log-level", default="INFO")
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("collect", help="pull data from GoldRush (needs GOLDRUSH_API_KEY)")
    c.add_argument("--stage", default="all", choices=["all", "protocol", "scan", "holders", "prices", "accounts", "livepeer", "akash", "solana", "state", "escrow", "extras", "boundaries", "collateral"])
    c.set_defaults(fn=cmd_collect)
    sub.add_parser("freeze", help="write data/frozen + SHA-256 manifest from data/raw").set_defaults(fn=cmd_freeze)
    sub.add_parser("analyze", help="results, figures and paper tables from data/frozen").set_defaults(fn=cmd_analyze)
    sub.add_parser("verify", help="re-check GoldRush data against public RPC nodes (no key needed)").set_defaults(
        fn=cmd_verify)
    sub.add_parser("scan-secrets", help="fail if an API key is present outside .env").set_defaults(fn=cmd_scan)
    a = p.parse_args(argv)
    logging.basicConfig(level=a.log_level, format="%(asctime)s %(levelname)s %(message)s", stream=sys.stderr)
    for noisy in ("urllib3", "matplotlib", "fontTools", "PIL"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    try:
        return a.fn(a)
    except MissingKeyError as e:
        log.error("%s", e)
        return MISSING_KEY
    except ApiError as e:
        log.error("%s", e)
        return API_ERROR
