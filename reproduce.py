#!/usr/bin/env python3
"""Reproduce every number, table and figure in the paper from data/frozen.
No API key and no network needed. Optionally compile the PDF (needs pdflatex and bibtex)."""
import argparse
import logging
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from compute_forensics.freeze import verify  # noqa: E402
from compute_forensics.pipeline import run  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--compile", action="store_true", help="also build paper/main.pdf with pdflatex and bibtex")
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    for noisy in ("matplotlib", "fontTools", "PIL"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    bad = verify(ROOT / "data" / "frozen")
    if bad:
        print(f"Frozen data checksum mismatch: {bad}", file=sys.stderr)
        return 2
    run(ROOT / "data" / "frozen", ROOT / "results", ROOT / "paper")
    subprocess.run([sys.executable, str(ROOT / "scripts" / "fill_readme.py")], check=True)
    if a.compile:
        tex = ["pdflatex", "-interaction=nonstopmode", "-halt-on-error", "main.tex"]
        for cmd in (tex, ["bibtex", "main"], tex, tex):
            subprocess.run(cmd, cwd=ROOT / "paper", check=True, stdout=subprocess.DEVNULL)
        print("paper/main.pdf built")
    return 0


if __name__ == "__main__":
    sys.exit(main())
