"""Freeze the raw collection into data/frozen with a SHA-256 manifest so the
paper can be reproduced offline, byte for byte, without an API key."""
from __future__ import annotations

import gzip
import hashlib
import json
import shutil
from pathlib import Path

FILES = ["protocol_txs.json.gz", "hub_events.json.gz", "holders.json.gz", "prices.json.gz", "accounts.json.gz",
         "livepeer.json.gz", "akash.json.gz", "solana.json.gz", "state.json.gz", "escrow_trace.json.gz", "extras.json.gz",
         "collateral.json.gz"]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _canonical(src: Path, dst: Path) -> None:
    """Re-encode with sorted keys and a fixed gzip mtime so the hash is stable."""
    with gzip.open(src, "rt", encoding="utf-8") as fh:
        obj = json.load(fh)
    raw = json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()
    with dst.open("wb") as out, gzip.GzipFile(fileobj=out, mode="wb", mtime=0, filename="") as gz:
        gz.write(raw)


def freeze(raw: Path, frozen: Path) -> None:
    frozen.mkdir(parents=True, exist_ok=True)
    lines = []
    for name in FILES:
        src = raw / name
        if not src.exists():
            raise FileNotFoundError(f"missing {src}; run `collect` first")
        dst = frozen / name
        _canonical(src, dst)
        lines.append(f"{sha256(dst)}  {name}")
    (frozen / "MANIFEST.sha256").write_text("\n".join(lines) + "\n")


def verify(frozen: Path) -> list[str]:
    bad = []
    for line in (frozen / "MANIFEST.sha256").read_text().splitlines():
        digest, name = line.split("  ", 1)
        if sha256(frozen / name) != digest:
            bad.append(name)
    return bad


def copy_external(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dst)
