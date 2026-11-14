#!/usr/bin/env python3
"""Fetch ASL Citizen poses (SorensenAI/asl-citizen-poses, MediaPipe Holistic .pose) for our vocabulary and convert
them to our clip format (data/asl_citizen/landmarks/<GLOSS>/<id>.npz, source "asl_citizen").

    PYTHONPATH=core core/.venv/bin/python core/tools/get_asl_citizen.py [--workers 8]

ASL Citizen is released for non-commercial research: fine for the prototype, not for a product.
Layout of the 576 points: pose 0-32, face 33-500, left hand 501-521, right hand 522-542, world pose 543-575.
Coordinates are pixels of the header frame; divided by its width/height so they match PopSign's 0-1 image coords.
"""
from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "core"))

from signer_core.model import read_vocab  # noqa: E402
from signer_core.vision.clip import save_clip  # noqa: E402

HF = "SorensenAI/asl-citizen-poses"
OUT = REPO / "data" / "asl_citizen"
ALIAS = {"THANK YOU": "THANKYOU", "THANKYOU": "THANKYOU", "TOILET": "POTTY", "BATHROOM": "POTTY"}
ROWS = np.r_[0:33, 501:522, 522:543]


def gloss_of(name: str) -> str:
    g = name.rsplit("/", 1)[-1][:-5].split("-", 1)[-1]  # '<id>-<GLOSS>.pose'
    return re.sub(r"\s*\d+$", "", g).upper().strip()


def convert(path: Path, gloss: str) -> Path:
    from pose_format import Pose

    with open(path, "rb") as f:
        p = Pose.read(f.read())
    d = p.header.dimensions
    xyz = np.asarray(p.body.data.filled(np.nan))[:, 0, ROWS, :].astype(np.float32)
    conf = np.asarray(p.body.confidence)[:, 0, ROWS]
    xyz[conf <= 0] = np.nan
    xyz[..., 0] /= d.width
    xyz[..., 1] /= d.height
    xyz[..., 2] /= d.width  # MediaPipe z is in x units
    fps = float(p.body.fps) or 30.0
    t_ms = np.round(np.arange(len(xyz)) * 1000.0 / fps).astype(np.int64)
    out = OUT / "landmarks" / gloss / (path.stem.replace(" ", "_") + ".npz")  # full stem: ids repeat across batches
    # signer ids are anonymised away; the batch folder is the closest grouping we have
    return save_clip(out, xyz, t_ms, fps, gloss, path.parent.name, "asl_citizen")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()
    from huggingface_hub import HfApi, hf_hub_download

    vocab = set(read_vocab(str(REPO / "data" / "VOCAB.md"))) - {"REST"}
    files = [f for f in HfApi().list_repo_files(HF, repo_type="dataset") if f.endswith(".pose") and "anonymized" not in f]  # anonymized/ repeats 193 clips
    sel = [(f, ALIAS.get(gloss_of(f), gloss_of(f))) for f in files]
    sel = [(f, g) for f, g in sel if g in vocab]
    print(f"{len(files)} pose files, {len(sel)} for our vocabulary", flush=True)

    def job(fg):
        f, g = fg
        try:
            return g, convert(Path(hf_hub_download(HF, f, repo_type="dataset", local_dir=str(OUT / "raw"))), g)
        except Exception as e:  # noqa: BLE001 - count and keep going
            print("fail", f, e, flush=True)
            return g, None

    n = Counter()
    bad = 0
    with ThreadPoolExecutor(args.workers) as ex:
        for i, (g, out) in enumerate(ex.map(job, sel), 1):
            if out is None:
                bad += 1
            else:
                n[g] += 1
            if i % 100 == 0:
                print(f"{i}/{len(sel)}", flush=True)
    print(dict(sorted(n.items())), f"total={sum(n.values())} failed={bad}")


if __name__ == "__main__":
    main()
