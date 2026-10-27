#!/usr/bin/env python3
"""Fill the numbers in README.md and RESEARCH.md from paper/generated/numbers.tex.

Every number that also appears in the paper is wrapped in the Markdown source as
    <!--n:MacroName-->value<!--/n-->
The markers are invisible when rendered. This script replaces each value with the
current macro, so the README, the ledger and the paper can never disagree.
`reproduce.py` runs it after regenerating the macros."""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MACROS = ROOT / "paper" / "generated" / "numbers.tex"
FILES = [ROOT / "README.md", ROOT / "RESEARCH.md"]


def macros() -> dict[str, str]:
    out = {}
    for name, val in re.findall(r"\\newcommand\{\\(\w+)\}\{(.*)\}", MACROS.read_text()):
        v = val.replace(r"\,", "").replace(r"\%", "%").replace(r"\$", "$").replace("~", " ")
        v = re.sub(r"\\ldots\{\}", "...", v)
        v = re.sub(r"\\textsuperscript\{(\w+)\}", r"^\1", v)
        out[name] = re.sub(r"\\(\w+)\{\}", "", v)
    return out


def fill(path: Path, m: dict[str, str]) -> int:
    text = path.read_text()
    missing = []

    def sub(match):
        key = match.group(1)
        if key not in m:
            missing.append(key)
            return match.group(0)
        return f"<!--n:{key}-->{m[key]}<!--/n-->"

    new = re.sub(r"<!--n:(\w+)-->.*?<!--/n-->", sub, text, flags=re.S)
    if missing:
        print(f"{path.name}: no macro for {sorted(set(missing))}", file=sys.stderr)
    if new != text:
        path.write_text(new)
    return len(re.findall(r"<!--n:", new))


def main() -> int:
    m = macros()
    for p in FILES:
        if p.exists():
            print(f"{p.name}: {fill(p, m)} numbers filled")
    return 0


if __name__ == "__main__":
    sys.exit(main())
