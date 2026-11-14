"""M4 D3: every percentage / rate in the deck source must come from eval/results.

Finds every `NN%` / `NN.N%` and every `0.NN` decimal in deck/signer.html and checks that some
numeric value in eval/results/final.json or eval/results/m*.json rounds to it (a rate r matches
`NN%` if round(100*r) == NN at the shown precision, and `0.NN` if round(r, 2) == 0.NN).
Exit 0 if all match, 1 otherwise (listing the unmatched numbers).
"""
from __future__ import annotations

import glob
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DECK = os.path.join(ROOT, "deck", "signer.html")
RESULTS = os.path.join(ROOT, "eval", "results")

PCT = re.compile(r"(?<![\d.])(\d{1,3}(?:\.\d+)?)\s?%")
DEC = re.compile(r"(?<![\d.])(0\.\d+)(?![\d])")


def result_values(results_dir: str = RESULTS) -> list[float]:
    files = sorted(glob.glob(os.path.join(results_dir, "m*.json")))
    final = os.path.join(results_dir, "final.json")
    if os.path.exists(final):
        files.append(final)
    vals: list[float] = []
    for f in files:
        with open(f) as fh:
            d = json.load(fh)
        # Headline metrics only: top-level scalars, plus scalars one level down in dict-valued
        # entries that are not per-class breakdowns (e.g. {"bigru": {"top1": ..}}). Per-class
        # numbers are excluded so a headline claim cannot match a coincidental class score.
        for k, v in d.items():
            if k == "per_class":
                continue
            if isinstance(v, dict):
                vals += [float(x) for x in v.values() if isinstance(x, (int, float)) and not isinstance(x, bool)]
            elif isinstance(v, (int, float)) and not isinstance(v, bool):
                vals.append(float(v))
    return vals


def deck_text(path: str = DECK) -> str:
    with open(path) as fh:
        html = fh.read()
    html = re.sub(r"<style.*?</style>", " ", html, flags=re.S)  # CSS sizes are not claims
    html = re.sub(r"<!--.*?-->", " ", html, flags=re.S)
    return re.sub(r"<[^>]+>", " ", html)


def claims(text: str) -> list[tuple[str, float, int]]:
    """(shown text, value as a rate, decimals of the rate) for every number in the deck."""
    out = []
    for m in PCT.finditer(text):
        s = m.group(1)
        d = len(s.split(".")[1]) if "." in s else 0
        out.append((s + "%", float(s) / 100, d + 2))
    for m in DEC.finditer(text):
        s = m.group(1)
        out.append((s, float(s), len(s.split(".")[1])))
    return out


def unmatched(text: str, vals: list[float]) -> list[str]:
    bad = []
    for shown, rate, nd in claims(text):
        if not any(abs(round(v, nd) - rate) < 1e-9 for v in vals):
            bad.append(shown)
    return bad


def main() -> int:
    vals = result_values()
    text = deck_text()
    found = claims(text)
    bad = unmatched(text, vals)
    print(f"deck numbers: {[c[0] for c in found]}")
    if bad:
        print(f"FAIL: not in eval/results/final.json or m*.json: {bad}")
        return 1
    print("PASS: every deck number appears in eval/results")
    return 0


if __name__ == "__main__":
    sys.exit(main())
