#!/usr/bin/env python3
"""Pick the large vocabulary from ASL Citizen's gloss counts by English word frequency.

    PYTHONPATH=core core/.venv/bin/python core/tools/pick_vocab_large.py --n 600 [--counts /tmp/ac_counts.json]

Keeps single-word glosses with >= --min-clips clips, drops fingerspelling letters, numbers and the
words of our current 24, ranks the rest by wordfreq (zipf) and writes data/VOCAB_LARGE.md.
The 24 core glosses always come first (their ASL Citizen names are mapped below).
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from wordfreq import zipf_frequency

REPO = Path(__file__).resolve().parents[2]
CORE = ["HELLO", "BYE", "YES", "NO", "PLEASE", "THANKYOU", "WAIT", "FINISH", "POTTY", "WATER", "WHERE", "WHY",
        "WHO", "TIME", "BOOK", "LISTEN", "TALK", "HOME", "SICK", "HAPPY", "HELP", "QUESTION", "UNDERSTAND", "AGAIN"]
# our gloss -> ASL Citizen gloss
AC_NAME = {"THANKYOU": "THANK YOU", "POTTY": "BATHROOM", "FINISH": "FINISH"}
# tokens that are not everyday words: names, places, profanity
DROP = {"BITCH", "BULLSHIT", "SHIT", "FUCK", "DAMN", "ASS"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=600)
    ap.add_argument("--min-clips", type=int, default=25)
    ap.add_argument("--counts", default="/tmp/ac_counts.json")
    ap.add_argument("--out", default=str(REPO / "data" / "VOCAB_LARGE.md"))
    a = ap.parse_args()
    counts = json.load(open(a.counts))
    rows, seen = [], set()
    for g in CORE:
        ac = AC_NAME.get(g, g)
        rows.append((g, ac, counts.get(ac, 0), "core"))
        seen.add(ac)
    cand = []
    for g, n in counts.items():
        if g in seen or n < a.min_clips or g in DROP:
            continue
        if not re.fullmatch(r"[A-Z]{3,}", g):  # single word, no digits/underscores/spaces
            continue
        cand.append((zipf_frequency(g.lower(), "en"), g, n))
    cand.sort(reverse=True)
    for _, g, n in cand[: a.n - len(CORE)]:
        rows.append((g, g, n, ""))
    lines = ["# Large vocabulary (ASL Citizen glosses)", "",
             f"{len(rows)} glosses: the {len(CORE)} core signs, then the most frequent English words that have >= {a.min_clips} ASL Citizen clips.",
             "`GLOSS` is our label, `ac_gloss` the ASL Citizen name, `core` marks the demo signs.", "",
             "| GLOSS | ac_gloss | n_clips | note |", "|---|---|---|---|"]
    lines += [f"| {g} | {ac} | {n} | {note} |" for g, ac, n, note in rows]
    Path(a.out).write_text("\n".join(lines) + "\n")
    miss = [g for g, ac, n, note in rows if note == "core" and n == 0]
    print(len(rows), "glosses; core missing in ASL Citizen:", miss, "; clips:", sum(r[2] for r in rows))


if __name__ == "__main__":
    main()
