"""Export the GRU for the static browser demo (site/): weights as float32 binary + manifest, plus test vectors.

    PYTHONPATH=core core/.venv/bin/python core/tools/export_web.py [--ckpt data/models/gru.pt] [--out site/model]

site/model/gru.json   classes, mean, std, hidden, tensor name -> [offset, shape] into gru.bin
site/model/gru.bin    all weights, float32 little endian
site/model/testvec.json  real clips + stitched streams with the Python probabilities / segments; `node site/test.mjs`
                         replays them through the JS port and fails on any difference.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import torch

from signer_core.model.gru import GRUClassifier
from signer_core.model.segmenter import Segmenter


def jsonable(a):
    return np.where(np.isnan(a), None, np.round(a, 5)).tolist()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ckpt", default="data/models/gru.pt")
    ap.add_argument("--out", default="site/model")
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    ck = torch.load(args.ckpt, map_location="cpu", weights_only=False)
    chunks, tensors, off = [], {}, 0
    for name, t in ck["state"].items():
        a = t.numpy().astype("<f4")
        tensors[name] = [off, list(a.shape)]
        chunks.append(a.ravel())
        off += a.size
    (out / "gru.bin").write_bytes(np.concatenate(chunks).tobytes())
    hidden = int(ck.get("hidden") or 128)
    (out / "gru.json").write_text(json.dumps({
        "classes": list(ck["classes"]), "hidden": hidden, "mean": np.asarray(ck["mean"]).tolist(),
        "std": np.asarray(ck["std"]).tolist(), "tensors": tensors}))

    # test vectors: one clip per few glosses, the Python probabilities, and a stitched stream
    clf = GRUClassifier(args.ckpt)
    paths = sorted(Path("data/popsign/landmarks").glob("*/*.npz"))
    rng = np.random.default_rng(0)
    picks = [paths[i] for i in rng.choice(len(paths), 4, replace=False)] + sorted(Path("data/taught").glob("*/0.npz"))[:2]
    clips = []
    for p in picks:
        xyz = np.load(p)["xyz"].astype(np.float32)
        proba = clf.predict_proba(xyz)
        clips.append({"path": str(p), "xyz": jsonable(xyz), "proba": [proba[c] for c in clf._classes]})

    a = np.load(picks[0])["xyz"].astype(np.float32)
    b = np.load(picks[1])["xyz"].astype(np.float32)
    rest = a[:1].copy()
    rest[:, 33:75] = np.nan  # shoulders and hips tracked, hands gone
    stream = np.concatenate([np.repeat(rest, 8, 0), a, np.repeat(rest, 12, 0), b, np.repeat(rest, 12, 0)])
    ts = np.arange(len(stream)) * 66
    seg, segs = Segmenter(), []
    for f, t in zip(stream, ts):
        s = seg.push(f, int(t))
        if s is not None:
            segs.append({"start_ms": s.start_ms, "end_ms": s.end_ms, "n": len(s.xyz),
                         "proba": [clf.predict_proba(s.xyz)[c] for c in clf._classes]})
    s = seg.flush()
    if s is not None:
        segs.append({"start_ms": s.start_ms, "end_ms": s.end_ms, "n": len(s.xyz),
                     "proba": [clf.predict_proba(s.xyz)[c] for c in clf._classes]})
    (out / "testvec.json").write_text(json.dumps({
        "classes": clf._classes, "clips": clips,
        "stream": {"xyz": jsonable(stream), "ts": ts.tolist(), "segments": segs}}))
    print(f"gru.bin {off * 4 / 1e6:.1f} MB, {len(clips)} clips, {len(segs)} stream segments")


if __name__ == "__main__":
    main()
