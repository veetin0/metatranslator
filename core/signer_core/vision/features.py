"""Landmark clip -> fixed-size feature vector for kNN / small classifiers (CONTRACTS.md section 5). numpy only.

Per frame (F = 180 numbers, see FEATURE_NAMES):
  * upper-body pose points (nose, both shoulders, elbows, wrists) = 7 x 3
  * left hand 21 x 3 and right hand 21 x 3
    all as (xyz - shoulder midpoint) / shoulder width (x, y and z share the one scale, so a signer standing
    nearer or farther gives the same numbers). Shoulders of a frame that has none are carried over from the
    nearest frame that has them; a clip with no shoulders at all uses centre (0.5, 0.5, 0) and width 0.25.
  * hand joint angles: 5 fingers x 3 interior joints per hand (arccos of the cosine, divided by pi, so in [0, 1])
  * presence flags [pose, left hand, right hand] (1.0 / 0.0)
A block that is missing (NaN) in a frame is all zeros with flag 0, never NaN.

`clip_features` then resamples the time axis to RESAMPLE_STEPS (32) by linear interpolation that only mixes
frames where the block is present (a hand that appears halfway does not blend with zeros); a resampled step
counts as present when at least half of its interpolation weight was on present frames.

Known limit: x and y are normalised by image width and height separately, so on a non-square frame the
shoulder-width scale is slightly anisotropic. It is the same for every producer of the layout; fine for kNN.
"""
from __future__ import annotations

import numpy as np

from ..contracts import LEFT_HAND, N_POINTS, RESAMPLE_STEPS, RIGHT_HAND

POSE_KEEP = (0, 11, 12, 13, 14, 15, 16)  # nose, L/R shoulder, L/R elbow, L/R wrist
L_SHOULDER, R_SHOULDER = 11, 12
# (wrist, base, ..., tip) chains of MediaPipe's 21 hand points; angles at the 3 interior joints of each
_FINGERS = ((0, 1, 2, 3, 4), (0, 5, 6, 7, 8), (0, 9, 10, 11, 12), (0, 13, 14, 15, 16), (0, 17, 18, 19, 20))
_DEFAULT_WIDTH = 0.25

N_POSE = len(POSE_KEEP) * 3  # 21
N_HAND_XYZ = 21 * 3  # 63
N_ANGLES = len(_FINGERS) * 3  # 15
N_HAND = N_HAND_XYZ + N_ANGLES  # 78 per hand (coordinates + angles)
FEATURE_DIM = N_POSE + 2 * N_HAND + 3  # 180
FEATURE_NAMES = (
    [f"pose{i}_{a}" for i in POSE_KEEP for a in "xyz"]
    + [f"lhand{i}_{a}" for i in range(21) for a in "xyz"]
    + [f"lhand_angle{i}" for i in range(N_ANGLES)]
    + [f"rhand{i}_{a}" for i in range(21) for a in "xyz"]
    + [f"rhand_angle{i}" for i in range(N_ANGLES)]
    + ["pose_present", "lhand_present", "rhand_present"]
)
assert len(FEATURE_NAMES) == FEATURE_DIM

# column blocks: (start, stop) of each presence-gated block inside the F axis
_POSE_COLS = (0, N_POSE)
_LH_COLS = (N_POSE, N_POSE + N_HAND)
_RH_COLS = (N_POSE + N_HAND, N_POSE + 2 * N_HAND)
_FLAG_COLS = (N_POSE + 2 * N_HAND, FEATURE_DIM)


def _fill_nearest(valid: np.ndarray, vals: np.ndarray) -> np.ndarray:
    """Replace entries where ~valid with the value of the nearest valid index (vals: (T, ...))."""
    if valid.all() or not valid.any():
        return vals
    good = np.flatnonzero(valid)
    pos = np.arange(len(valid))
    nearest = good[np.abs(pos[:, None] - good[None, :]).argmin(axis=1)]
    return vals[nearest]


def _shoulder_frame(xyz: np.ndarray):
    """Per-frame (centre (T,3), width (T,)) from the shoulders, filled from the nearest valid frame."""
    ls, rs = xyz[:, L_SHOULDER], xyz[:, R_SHOULDER]
    valid = ~(np.isnan(ls).any(axis=1) | np.isnan(rs).any(axis=1))
    centre = (ls + rs) / 2
    width = np.linalg.norm(ls - rs, axis=1)
    valid &= np.isfinite(width) & (width > 1e-4)
    if not valid.any():
        t = xyz.shape[0]
        return np.tile(np.array([0.5, 0.5, 0.0], dtype=np.float32), (t, 1)), np.full(t, _DEFAULT_WIDTH, np.float32)
    centre = np.where(valid[:, None], centre, 0.0)
    width = np.where(valid, width, 1.0)
    return _fill_nearest(valid, centre), _fill_nearest(valid, width)


def _hand_angles(h: np.ndarray) -> np.ndarray:
    """(T, 21, 3) -> (T, 15) joint angles / pi."""
    out = []
    for chain in _FINGERS:
        for k in range(1, 4):
            a = h[:, chain[k - 1]] - h[:, chain[k]]
            b = h[:, chain[k + 1]] - h[:, chain[k]]
            cos = (a * b).sum(-1) / (np.linalg.norm(a, axis=-1) * np.linalg.norm(b, axis=-1) + 1e-9)
            out.append(np.arccos(np.clip(cos, -1.0, 1.0)) / np.pi)
    return np.stack(out, axis=1)


def frame_features(xyz) -> np.ndarray:
    """(T, 75, 3) landmarks (NaN = missing) -> (T, FEATURE_DIM) float32, NaN-free, before time resampling."""
    xyz = np.asarray(xyz, dtype=np.float32)
    if xyz.ndim != 3 or xyz.shape[1:] != (N_POINTS, 3):
        raise ValueError(f"xyz must be (T, {N_POINTS}, 3), got {xyz.shape}")
    t = xyz.shape[0]
    centre, width = _shoulder_frame(xyz)
    norm = (xyz - centre[:, None, :]) / width[:, None, None]

    out = np.zeros((t, FEATURE_DIM), dtype=np.float32)
    flags = np.zeros((t, 3), dtype=np.float32)

    pose = norm[:, list(POSE_KEEP)]
    ok = ~np.isnan(pose).any(axis=(1, 2))
    out[ok, _POSE_COLS[0]:_POSE_COLS[1]] = pose[ok].reshape(-1, N_POSE)
    flags[:, 0] = ok

    for col, rows, f in ((_LH_COLS, LEFT_HAND, 1), (_RH_COLS, RIGHT_HAND, 2)):
        hand = norm[:, rows.start:rows.stop]
        ok = ~np.isnan(hand).any(axis=(1, 2))
        if ok.any():
            block = np.concatenate([hand[ok].reshape(-1, N_HAND_XYZ), _hand_angles(hand[ok])], axis=1)
            out[ok, col[0]:col[1]] = block
        flags[:, f] = ok
    out[:, _FLAG_COLS[0]:_FLAG_COLS[1]] = flags
    return out


def _resample(feat: np.ndarray, steps: int) -> np.ndarray:
    t = feat.shape[0]
    u = np.linspace(0.0, t - 1, steps) if t > 1 else np.zeros(steps)
    lo = np.floor(u).astype(int)
    hi = np.minimum(lo + 1, t - 1)
    frac = (u - lo)[:, None].astype(np.float32)

    def interp(a):
        return a[lo] * (1 - frac) + a[hi] * frac

    out = np.zeros((steps, feat.shape[1]), dtype=np.float32)
    for (c0, c1), flag in ((_POSE_COLS, 0), (_LH_COLS, 1), (_RH_COLS, 2)):
        p = feat[:, _FLAG_COLS[0] + flag][:, None]  # (T, 1) presence
        w = interp(p)  # share of interpolation weight on present frames
        num = interp(feat[:, c0:c1] * p)  # absent frames are zeros already
        present = (w >= 0.5).astype(np.float32)
        out[:, c0:c1] = np.where(present > 0, num / np.maximum(w, 1e-6), 0.0)
        out[:, _FLAG_COLS[0] + flag] = present[:, 0]
    return out


def clip_features(xyz, steps: int = RESAMPLE_STEPS) -> np.ndarray:
    """(T, 75, 3) -> (steps, FEATURE_DIM) float32. NaN-safe: missing blocks are zeros with presence flag 0."""
    feat = frame_features(xyz)
    if feat.shape[0] < 1:
        raise ValueError("clip has no frames")
    return _resample(feat, steps)


def flat_features(xyz, steps: int = RESAMPLE_STEPS) -> np.ndarray:
    """`clip_features` flattened to (steps * FEATURE_DIM,) for kNN."""
    return clip_features(xyz, steps).reshape(-1)


def _selfcheck() -> None:
    rng = np.random.default_rng(0)

    def person(t):
        a = np.full((t, N_POINTS, 3), np.nan, dtype=np.float32)
        pose = rng.random((33, 3)).astype(np.float32) * 0.1
        pose[L_SHOULDER] = (0.6, 0.5, 0.0)
        pose[R_SHOULDER] = (0.4, 0.5, 0.0)
        hand_l, hand_r = rng.random((21, 3)).astype(np.float32), rng.random((21, 3)).astype(np.float32)
        a[:, 0:33], a[:, 33:54], a[:, 54:75] = pose, hand_l, hand_r
        return a

    base = person(20)
    f = clip_features(base)
    assert f.shape == (RESAMPLE_STEPS, FEATURE_DIM) and f.dtype == np.float32 and np.isfinite(f).all()
    assert flat_features(base).shape == (RESAMPLE_STEPS * FEATURE_DIM,)
    assert (f[:, -3:] == 1).all()
    # translation and uniform scale invariance (shoulder-centred, shoulder-width-scaled)
    g = clip_features(base * np.float32(1.7) + np.float32(0.2))
    assert np.allclose(f, g, atol=1e-4), float(np.abs(f - g).max())
    # missing hand -> zeros + flag 0, no NaN; missing everything -> all zeros
    miss = base.copy()
    miss[:, 54:75] = np.nan
    fm = clip_features(miss)
    assert np.isfinite(fm).all() and (fm[:, _RH_COLS[0]:_RH_COLS[1]] == 0).all() and (fm[:, -1] == 0).all() and (fm[:, -2] == 1).all()
    none = clip_features(np.full((5, N_POINTS, 3), np.nan, dtype=np.float32))
    assert np.isfinite(none).all() and (none == 0).all()
    # a hand present only in the second half does not blend with zeros
    half = base.copy()
    half[:10, 33:54] = np.nan
    fh = clip_features(half)
    assert fh[0, -2] == 0 and fh[-1, -2] == 1
    assert np.allclose(fh[-1, _LH_COLS[0]:_LH_COLS[1]], f[-1, _LH_COLS[0]:_LH_COLS[1]], atol=1e-4)
    # T=1, T=2 and float16 input
    assert clip_features(base[:1]).shape == (RESAMPLE_STEPS, FEATURE_DIM)
    assert clip_features(base[:2].astype(np.float16)).shape == (RESAMPLE_STEPS, FEATURE_DIM)
    # a straight finger is ~180 degrees (1.0), a folded one is smaller
    hand = np.zeros((1, 21, 3), dtype=np.float32)
    for chain in _FINGERS:
        for k, i in enumerate(chain):
            hand[0, i] = (0.0, -0.1 * k, 0.0)
    assert np.allclose(_hand_angles(hand), 1.0, atol=1e-3)
    print("features selfcheck ok", f.shape)


if __name__ == "__main__":
    _selfcheck()
