"""Turn frozen raw logs into one ordered, de-duplicated list of decoded events."""
from __future__ import annotations

from dataclasses import dataclass, field

from .abi import decode_log


@dataclass(order=True)
class Ev:
    block: int
    index: int
    time: str = field(compare=False)
    tx: str = field(compare=False)
    sender: str = field(compare=False)      # contract that emitted the log
    tx_from: str = field(compare=False)     # EOA / contract that sent the transaction
    name: str = field(compare=False)
    f: dict = field(compare=False)
    raw_topics: tuple = field(compare=False, default=())
    raw_data: str = field(compare=False, default="0x")

    @property
    def content(self) -> tuple:
        """The log's identity by content. GoldRush's log offsets can differ between its
        endpoints (and from the RPC's logIndex) for the same log, so we never merge on them."""
        return (self.tx.lower(), self.sender.lower(), tuple(t.lower() for t in self.raw_topics),
                (self.raw_data or "0x").lower())


def from_protocol_txs(protocol_txs: dict) -> list[Ev]:
    seen, out = set(), []
    for txs in protocol_txs.values():
        for t in txs:
            if t.get("ok") is False:
                continue
            for lg in t["logs"]:
                key = (lg["h"], lg["i"])
                if key in seen:
                    continue
                seen.add(key)
                d = decode_log(lg["tp"], lg["d"])
                if d:
                    out.append(Ev(t["b"] or 0, lg["i"] or 0, t["t"], t["h"], lg["a"], t["f"], d[0], d[1],
                                  tuple(lg["tp"]), lg["d"] or "0x"))
    return sorted(out)


def from_scans(hub_events: dict) -> list[Ev]:
    seen, out = set(), []
    for logs in (hub_events.get("events") or {}).values():
        for lg in logs:
            key = (lg["h"], lg["i"])
            if key in seen:
                continue
            seen.add(key)
            d = decode_log(lg["tp"], lg["d"])
            if d:
                out.append(Ev(lg["b"] or 0, lg["i"] or 0, lg["t"], lg["h"], lg["a"], "", d[0], d[1],
                              tuple(lg["tp"]), lg["d"] or "0x"))
    return sorted(out)


def merge(*lists: list[Ev]) -> list[Ev]:
    """Union of several sources. A log seen in more than one source is kept once; a
    log that legitimately repeats inside one transaction keeps its multiplicity."""
    from collections import Counter
    kept: Counter = Counter()
    out = []
    for lst in lists:
        here = Counter(e.content for e in lst)
        used: Counter = Counter()
        for e in lst:
            k = e.content
            used[k] += 1
            if used[k] > kept[k] and used[k] <= here[k]:
                out.append(e)
        for k, n in here.items():
            kept[k] = max(kept[k], n)
    return sorted(out)
