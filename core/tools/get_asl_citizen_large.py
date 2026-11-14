#!/usr/bin/env python3
"""Fetch ASL Citizen poses for the large vocabulary (data/VOCAB_LARGE.md) and convert them to clip npz files
(data/asl_citizen_large/landmarks/<GLOSS>/<stem>.npz, source "asl_citizen"). Raw .pose files are deleted after conversion.

    PYTHONPATH=core core/.venv/bin/python core/tools/get_asl_citizen_large.py [--workers 16] [--max-per-gloss 40] [--limit N]

Non-commercial research data (ASL Citizen). Conversion matches get_asl_citizen.py.
"""
from __future__ import annotations

import argparse
import re
import sys
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "core"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import get_asl_citizen as ac  # noqa: E402  (ROWS, gloss_of, HF)
import numpy as np  # noqa: E402
from signer_core.vision.clip import save_clip  # noqa: E402

OUT = REPO / "data" / "asl_citizen_large"


def read_table(path):
    """{asl_citizen_gloss: our GLOSS} from VOCAB_LARGE.md."""
    m = {}
    for line in Path(path).read_text().splitlines():
        c = [x.strip() for x in line.strip("|").split("|")]
        if len(c) >= 3 and c[0] and re.fullmatch(r"[A-Z]+", c[0]) and c[2].isdigit():
            m[c[1]] = c[0]
    return m


def convert(path: Path, gloss: str):
    from pose_format import Pose

    with open(path, "rb") as f:
        p = Pose.read(f.read())
    d = p.header.dimensions
    xyz = np.asarray(p.body.data.filled(np.nan))[:, 0, ac.ROWS, :].astype(np.float32)
    conf = np.asarray(p.body.confidence)[:, 0, ac.ROWS]
    xyz[conf <= 0] = np.nan
    xyz[..., 0] /= d.width
    xyz[..., 1] /= d.height
    xyz[..., 2] /= d.width
    fps = float(p.body.fps) or 30.0
    t_ms = np.round(np.arange(len(xyz)) * 1000.0 / fps).astype(np.int64)
    out = OUT / "landmarks" / gloss / (path.stem.replace(" ", "_") + ".npz")
    return save_clip(out, xyz, t_ms, fps, gloss, path.parent.name, "asl_citizen")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--vocab", default=str(REPO / "data" / "VOCAB_LARGE.md"))
    ap.add_argument("--workers", type=int, default=16)
    ap.add_argument("--max-per-gloss", type=int, default=40)
    ap.add_argument("--limit", type=int, default=None, help="only the first N glosses (smoke test)")
    a = ap.parse_args()
    from huggingface_hub import HfApi, hf_hub_download

    table = read_table(a.vocab)
    if a.limit:
        table = dict(list(table.items())[: a.limit])
    files = [f for f in HfApi().list_repo_files(ac.HF, repo_type="dataset") if f.endswith(".pose") and "anonymized" not in f]
    by = defaultdict(list)
    for f in sorted(files):
        g = table.get(ac.gloss_of(f))
        if g:
            by[g].append(f)
    sel = [(f, g) for g, fs in by.items() for f in fs[: a.max_per_gloss]]
    print(f"{len(table)} glosses, {len(sel)} pose files", flush=True)

    def job(fg):
        f, g = fg
        dst = OUT / "landmarks" / g / (Path(f).stem.replace(" ", "_") + ".npz")
        if dst.exists():
            return g, dst
        try:
            raw = Path(hf_hub_download(ac.HF, f, repo_type="dataset", local_dir=str(OUT / "raw")))
            r = convert(raw, g)
            raw.unlink(missing_ok=True)
            return g, r
        except Exception as e:  # noqa: BLE001
            print("fail", f, e, flush=True)
            return g, None

    n, bad = Counter(), 0
    with ThreadPoolExecutor(a.workers) as ex:
        for i, (g, out) in enumerate(ex.map(job, sel), 1):
            if out is None:
                bad += 1
            else:
                n[g] += 1
            if i % 500 == 0:
                print(f"{i}/{len(sel)}", flush=True)
    print(f"glosses={len(n)} total={sum(n.values())} failed={bad}")


if __name__ == "__main__":
    main()
