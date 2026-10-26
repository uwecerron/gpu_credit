"""GoldRush endpoint wrappers used by the collectors. One function per endpoint.

  /v1/{chain}/address/{addr}/transactions_v3/page/{n}/        full tx history (page 0 = oldest)
  /v1/{chain}/address/{addr}/transactions_summary/            counts, first/last tx
  /v1/{chain}/events/topics/{topic}/?starting-block&ending-block&sender-address
                                                              log events by topic, <= 1,000,000 blocks per call
  /v1/{chain}/tokens/{token}/token_holders_v2/                current holder snapshot (paged)
  /v1/{chain}/block_v2/{date}/{date}/                         block height for a date
  /v1/pricing/historical_by_addresses_v2/{chain}/USD/{token}/ daily prices
"""
from __future__ import annotations

from typing import Iterator, Protocol

from .client import ApiError

MAX_BLOCK_SPAN = 1_000_000


class Getter(Protocol):
    def get(self, path: str, params: dict | None = None, cache: bool = True, cache_when=None): ...


def _has_next(data) -> bool:
    return bool(((data or {}).get("links") or {}).get("next"))


def slim_log(lg: dict) -> dict:
    return {
        "b": lg.get("block_height"), "t": lg.get("block_signed_at"), "h": (lg.get("tx_hash") or "").lower(),
        "i": lg.get("log_offset"), "a": (lg.get("sender_address") or "").lower(),
        "tk": lg.get("sender_contract_ticker_symbol"), "dc": lg.get("sender_contract_decimals"),
        "tp": [x.lower() for x in (lg.get("raw_log_topics") or [])], "d": lg.get("raw_log_data"),
    }


def slim_tx(tx: dict) -> dict:
    out = {
        "b": tx.get("block_height"), "t": tx.get("block_signed_at"), "h": (tx.get("tx_hash") or "").lower(),
        "f": (tx.get("from_address") or "").lower(), "to": (tx.get("to_address") or "").lower(),
        "v": str(tx.get("value") or "0"), "ok": tx.get("successful"),
        "logs": [],
    }
    for lg in tx.get("log_events") or []:
        s = slim_log(lg)
        s.update(b=out["b"], t=out["t"], h=out["h"])
        out["logs"].append(s)
    return out


def iter_transactions(api: Getter, chain: str, address: str, max_pages: int = 500,
                      with_logs: bool = True) -> Iterator[dict]:
    params = {"quote-currency": "USD"}
    if not with_logs:
        params["no-logs"] = "true"
    for page in range(max_pages):
        data = api.get(f"/v1/{chain}/address/{address}/transactions_v3/page/{page}/", params,
                       cache_when=_has_next)
        yield from data.get("items") or []
        if not _has_next(data):
            return
    raise ApiError(None, f"/v1/{chain}/address/{address}/transactions_v3/", f"more than {max_pages} pages")


def summary(api: Getter, chain: str, address: str, cache: bool = False) -> dict | None:
    items = api.get(f"/v1/{chain}/address/{address}/transactions_summary/", cache=cache).get("items") or []
    return items[0] if items else None


def block_at(api: Getter, chain: str, date: str) -> int:
    """Last block signed on `date` (UTC). block_v2 takes a [start, end) date range."""
    from datetime import date as _d, timedelta
    nxt = (_d.fromisoformat(date) + timedelta(days=1)).isoformat()
    items = api.get(f"/v1/{chain}/block_v2/{date}/{nxt}/", {"page-size": 1}).get("items") or []
    if not items:
        raise ApiError(None, f"/v1/{chain}/block_v2/{date}/", "no block for date")
    return int(items[0]["height"])


def windows(start: int, end: int, span: int = MAX_BLOCK_SPAN) -> list[tuple[int, int]]:
    """Inclusive, non-overlapping block windows covering [start, end]."""
    if end < start:
        return []
    out, lo = [], start
    while lo <= end:
        hi = min(lo + span - 1, end)
        out.append((lo, hi))
        lo = hi + 1
    return out


def events_by_topic(api: Getter, chain: str, topic: str, sender: str, lo: int, hi: int,
                    final: bool) -> list[dict]:
    """All logs with topic0 == topic emitted by `sender` in [lo, hi]. Windows that
    are entirely in the past (`final`) are cached; the open window never is.

    GoldRush treats `ending-block` as exclusive (verified: a log in block B is
    returned for [B, B+1] but not for [B, B]), so we ask for hi + 1."""
    out, page = [], 0
    while True:
        data = api.get(f"/v1/{chain}/events/topics/{topic}/",
                       {"starting-block": lo, "ending-block": hi + 1, "sender-address": sender,
                        "page-size": 1000, "page-number": page},
                       cache=final)
        out += [slim_log(x) for x in data.get("items") or []]
        pg = data.get("pagination") or {}
        if not pg.get("has_more"):
            return out
        page += 1


def holders(api: Getter, chain: str, token: str, max_pages: int = 1000) -> tuple[list[dict], int | None]:
    rows, block = [], None
    for page in range(max_pages):
        data = api.get(f"/v1/{chain}/tokens/{token}/token_holders_v2/", {"page-number": page}, cache=False)
        for it in data.get("items") or []:
            block = block or it.get("block_height")
            rows.append({"address": (it.get("address") or "").lower(), "balance": str(it.get("balance") or "0"),
                         "total_supply": str(it.get("total_supply") or "0")})
        if not (data.get("pagination") or {}).get("has_more"):
            return rows, block
    raise ApiError(None, f"/v1/{chain}/tokens/{token}/token_holders_v2/", "too many pages")


def daily_prices(api: Getter, chain: str, token: str, start: str, end: str) -> list[dict]:
    data = api.get(f"/v1/pricing/historical_by_addresses_v2/{chain}/USD/{token}/", {"from": start, "to": end},
                   cache=False)
    items = data if isinstance(data, list) else (data.get("items") or [])
    if not items:
        return []
    return sorted(({"date": p["date"], "price": p["price"]} for p in items[0].get("prices") or []
                   if p.get("price") is not None), key=lambda r: r["date"])
