#!/usr/bin/env python3
"""Fetch WLASL (Voxel51/WLASL, MP4) videos for our vocabulary, run Holistic on them and keep only landmarks
(data/wlasl/landmarks/<GLOSS>/<id>.npz, source "wlasl"). Videos are deleted after the npz is verified.

    PYTHONPATH=core core/.venv/bin/python core/tools/get_wlasl.py [--workers 28] [--limit N]

WLASL is released for non-commercial research (C-UDA): fine for the prototype, not for a product.
Signer ids are not in this copy; the `data_N` shard folder is stored as the closest grouping.
"""
from __future__ import annotations

import argparse
import json
import multiprocessing as mp
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "core"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import extract_landmarks as el  # noqa: E402
from signer_core.model import read_vocab  # noqa: E402

HF = "Voxel51/WLASL"
OUT = REPO / "data" / "wlasl"
ALIAS = {"thank you": "THANKYOU", "thankyou": "THANKYOU", "toilet": "POTTY", "bathroom": "POTTY"}


def select(vocab):
    from huggingface_hub import hf_hub_download

    d = json.load(open(hf_hub_download(HF, "samples.json", repo_type="dataset")))
    sel = []
    for s in d["samples"]:
        lab = str(s["gloss"]["label"]).strip().lower()
        g = ALIAS.get(lab, lab.upper())
        if g in vocab:
            sel.append((s["filepath"], g))
    return sel


def work(job):
    """Extract one downloaded video -> npz -> verify -> delete the video."""
    import os

    import numpy as np

    video, out_path, gloss, signer = job
    r = {"gloss": gloss, "clip": Path(out_path).stem, "status": "ok", "frames": 0}
    try:
        xyz, t_ms, fps = el.extract_video(
            video, lambda: el.HolisticRunner(el._STATE["backend"], el._STATE["model"]), el._STATE["max_side"]
        )
        r["frames"] = int(xyz.shape[0])
        if not (~np.isnan(xyz[:, : el.POSE_N, 0])).any():
            r["status"] = "no_pose"
            return r
        el.write_clip(out_path, xyz, t_ms, fps, gloss, signer, "wlasl")
        el.verify_clip(out_path, n_frames=xyz.shape[0], gloss=gloss, source="wlasl")
        os.remove(video)
    except Exception as e:  # noqa: BLE001 - one bad clip must not stop the batch
        r.update(status="failed", msg=f"{type(e).__name__}: {e}")
        Path(out_path).unlink(missing_ok=True)
    return r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()
    from huggingface_hub import hf_hub_download

    vocab = set(read_vocab(str(REPO / "data" / "VOCAB.md"))) - {"REST"}
    sel = select(vocab)
    if args.limit:
        sel = sel[: args.limit]
    print(f"{len(sel)} WLASL videos for our vocabulary", flush=True)

    def dl(fg):
        f, g = fg
        try:
            p = hf_hub_download(HF, f, repo_type="dataset", local_dir=str(OUT / "raw"))
        except Exception as e:  # noqa: BLE001
            print("fail", f, e, flush=True)
            return None
        shard = Path(f).parent.name
        return (p, str(OUT / "landmarks" / g / (Path(f).stem + ".npz")), g, "wl:" + shard)

    with ThreadPoolExecutor(12) as ex:
        jobs = [j for j in ex.map(dl, sel) if j]
    jobs = [j for j in jobs if not Path(j[1]).exists()]
    print(f"downloaded; {len(jobs)} to extract", flush=True)

    backend, model = el.choose_backend("auto")
    n, bad = Counter(), Counter()
    with mp.get_context("spawn").Pool(args.workers, el._init_worker, (backend, model, 960)) as pool:
        for i, r in enumerate(pool.imap_unordered(work, jobs), 1):
            (n if r["status"] == "ok" else bad)[r["gloss"] if r["status"] == "ok" else r["status"]] += 1
            if i % 50 == 0 or r["status"] != "ok":
                print(f"extract {i}/{len(jobs)} {r['gloss']}/{r['clip']} [{r['status']}] {r.get('msg', '')}", flush=True)
    print(dict(sorted(n.items())), f"total={sum(n.values())} bad={dict(bad)}")


if __name__ == "__main__":
    main()
