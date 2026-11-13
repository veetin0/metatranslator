"""Landmark clip files (.npz, CONTRACTS.md section 5). numpy only.

Keys: xyz float16 (T,75,3) | t_ms int64 (T,) strictly increasing | fps float32 scalar | gloss str |
signer str | source str in SOURCES. Missing pose/hand = NaN. Strings are stored as plain unicode arrays
(loadable with allow_pickle=False).
"""
from __future__ import annotations

import os
from pathlib import Path

import numpy as np

from ..contracts import CLIP_KEYS, N_POINTS

SOURCES = ("own", "popsign", "glasses", "webcam")


def _check(xyz, t_ms, fps, gloss, signer, source):
    """Validate already-typed values; raise ValueError on any problem."""
    if xyz.dtype != np.float16 or xyz.ndim != 3 or xyz.shape[1:] != (N_POINTS, 3) or xyz.shape[0] < 1:
        raise ValueError(f"xyz must be float16 (T>=1,{N_POINTS},3), got {xyz.dtype} {xyz.shape}")
    if np.isinf(xyz).any():
        raise ValueError("xyz contains inf (missing points must be NaN)")
    if t_ms.dtype != np.int64 or t_ms.shape != (xyz.shape[0],):
        raise ValueError(f"t_ms must be int64 ({xyz.shape[0]},), got {t_ms.dtype} {t_ms.shape}")
    if t_ms.shape[0] > 1 and not (np.diff(t_ms) > 0).all():
        raise ValueError("t_ms must be strictly increasing")
    if fps.dtype != np.float32 or fps.shape != () or not (np.isfinite(fps) and float(fps) > 0):
        raise ValueError(f"fps must be a positive float32 scalar, got {fps.dtype} {fps.shape} {fps}")
    if not gloss:
        raise ValueError("empty gloss")
    if not signer:
        raise ValueError("empty signer")
    if source not in SOURCES:
        raise ValueError(f"source {source!r} not in {SOURCES}")


def save_clip(path, xyz, t_ms, fps, gloss, signer, source) -> Path:
    """Write a clip atomically (temp file then rename). Coerces xyz->float16, t_ms->int64, fps->float32."""
    path = Path(path)
    xyz = np.asarray(xyz).astype(np.float16)
    t_ms = np.asarray(t_ms).astype(np.int64)
    fps = np.float32(fps)
    gloss, signer, source = str(gloss), str(signer), str(source)
    _check(xyz, t_ms, np.asarray(fps), gloss, signer, source)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".part")
    try:
        with open(tmp, "wb") as f:  # a file object: np.savez never appends '.npz' to the name
            np.savez_compressed(
                f, xyz=xyz, t_ms=t_ms, fps=fps, gloss=np.array(gloss), signer=np.array(signer), source=np.array(source)
            )
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()
    return path


def load_clip(path) -> dict:
    """Load and validate a clip. Returns {"xyz","t_ms","fps"(float),"gloss","signer","source"}."""
    with np.load(path, allow_pickle=False) as z:
        keys = set(z.files)
        if keys != set(CLIP_KEYS):
            raise ValueError(f"keys {sorted(keys)} != {sorted(CLIP_KEYS)}")
        xyz, t_ms, fps = z["xyz"], z["t_ms"], z["fps"]
        gloss, signer, source = str(z["gloss"]), str(z["signer"]), str(z["source"])
    _check(xyz, t_ms, fps, gloss, signer, source)
    return {"xyz": xyz, "t_ms": t_ms, "fps": float(fps), "gloss": gloss, "signer": signer, "source": source}


def validate_clip(path) -> bool:
    """True if `path` is a valid clip, else raises ValueError (so callers see why)."""
    load_clip(path)
    return True
