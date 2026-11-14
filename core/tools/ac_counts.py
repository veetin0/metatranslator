#!/usr/bin/env python3
"""Count ASL Citizen clips per gloss from the HF file listing (no download): writes /tmp/ac_counts.json for
pick_vocab_large.py. Same gloss rule as get_asl_citizen.gloss_of (strip variant digit, upper-case)."""
import json
import re
import sys
from collections import Counter

from huggingface_hub import HfApi

out = sys.argv[1] if len(sys.argv) > 1 else "/tmp/ac_counts.json"
c = Counter()
for f in HfApi().list_repo_files("SorensenAI/asl-citizen-poses", repo_type="dataset"):
    if f.endswith(".pose"):
        g = f.rsplit("/", 1)[-1][:-5].split("-", 1)[-1]
        c[re.sub(r"\s*\d+$", "", g).upper().strip()] += 1
json.dump(c, open(out, "w"))
print(len(c), "glosses,", sum(c.values()), "clips ->", out)
