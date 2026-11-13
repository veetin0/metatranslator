"""Prototype kNN over `flat_features` with calibrated confidence and top-k (CONTRACTS §5, tiers in contracts.py).

Clips are trimmed to their hand-active span, embedded (z-scored, unit norm) and compared by cosine similarity.
Confidence = distance-weighted vote share of the top class x a novelty factor that drops towards 0 when the
nearest prototype is further away than almost any training clip is from its own nearest neighbour.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

from ..contracts import LEFT_HAND, POSE, RESAMPLE_STEPS, RIGHT_HAND
from ..vision.features import flat_features

# MediaPipe Pose left/right pairs, swapped when mirroring a clip.
_POSE_PAIRS = ((1, 4), (2, 5), (3, 6), (7, 8), (9, 10), (11, 12), (13, 14), (15, 16), (17, 18), (19, 20),
               (21, 22), (23, 24), (25, 26), (27, 28), (29, 30), (31, 32))
_MIRROR_INDEX = np.arange(75)
for _a, _b in _POSE_PAIRS:
    _MIRROR_INDEX[_a], _MIRROR_INDEX[_b] = _b, _a
_MIRROR_INDEX[LEFT_HAND.start:LEFT_HAND.stop] = np.arange(RIGHT_HAND.start, RIGHT_HAND.stop)
_MIRROR_INDEX[RIGHT_HAND.start:RIGHT_HAND.stop] = np.arange(LEFT_HAND.start, LEFT_HAND.stop)
assert len(POSE) == 33


def mirror(xyz) -> np.ndarray:
    """Left-right mirror of a (T, 75, 3) clip: x -> 1 - x, left/right pose points and hands swapped."""
    out = np.asarray(xyz, dtype=np.float32)[:, _MIRROR_INDEX].copy()
    out[..., 0] = 1.0 - out[..., 0]
    return out


def hands_present(xyz) -> np.ndarray:
    """(T,) bool: at least one hand detected in the frame."""
    xyz = np.asarray(xyz, dtype=np.float32)
    lh = ~np.isnan(xyz[:, LEFT_HAND.start:LEFT_HAND.stop]).any(axis=(1, 2))
    rh = ~np.isnan(xyz[:, RIGHT_HAND.start:RIGHT_HAND.stop]).any(axis=(1, 2))
    return lh | rh


def trim_active(xyz, pad: int = 2) -> np.ndarray:
    """Cut leading/trailing frames without hands (keeps `pad` frames each side); unchanged if no hands at all."""
    xyz = np.asarray(xyz, dtype=np.float32)
    idx = np.flatnonzero(hands_present(xyz))
    if idx.size == 0:
        return xyz
    return xyz[max(0, idx[0] - pad): idx[-1] + pad + 1]


class KNNClassifier:
    """fit(clips, labels) / add(xyz, gloss) / predict_proba(xyz) / predict(xyz, top) / calibrate / save / load.

    `clips` are (T, 75, 3) landmark arrays (NaN = missing), labels are glosses (REST included if given).
    """

    name = "knn"

    def __init__(self, k: int = 7, temperature: float = 0.05, mirror: bool = True, steps: int = RESAMPLE_STEPS):
        self.k = k
        self.temperature = temperature
        self.mirror = mirror
        self.steps = steps
        self.mean: np.ndarray | None = None
        self.std: np.ndarray | None = None
        self.Z = np.zeros((0, 0), np.float32)
        self.labels: list[str] = []
        self.sim_lo, self.sim_hi = -1.0, 0.0

    # --- embedding -------------------------------------------------------------------------------------------
    def _raw(self, xyz) -> np.ndarray:
        return flat_features(trim_active(xyz), self.steps)

    def _embed(self, F: np.ndarray) -> np.ndarray:
        Z = (F - self.mean) / self.std
        return (Z / (np.linalg.norm(Z, axis=-1, keepdims=True) + 1e-9)).astype(np.float32)

    @property
    def classes(self) -> list[str]:
        return sorted(set(self.labels))

    # --- training --------------------------------------------------------------------------------------------
    def fit(self, clips, labels) -> "KNNClassifier":
        clips, labels = list(clips), [str(g) for g in labels]
        if not clips or len(clips) != len(labels):
            raise ValueError(f"need matching non-empty clips/labels, got {len(clips)}/{len(labels)}")
        feats, labs = [], []
        for xyz, g in zip(clips, labels):
            feats.append(self._raw(xyz)); labs.append(g)
            if self.mirror:
                feats.append(self._raw(mirror(xyz))); labs.append(g)
        F = np.stack(feats)
        self.mean = F.mean(axis=0)
        self.std = F.std(axis=0) + 1e-3
        self.Z = self._embed(F)
        self.labels = labs
        self._fit_novelty()
        return self

    def add(self, xyz, gloss: str) -> None:
        """Add one prototype (Teach-a-sign) using the existing feature statistics."""
        if self.mean is None:
            self.fit([xyz], [gloss])
            return
        rows = [self._raw(xyz)] + ([self._raw(mirror(xyz))] if self.mirror else [])
        self.Z = np.concatenate([self.Z, self._embed(np.stack(rows))])
        self.labels += [str(gloss)] * len(rows)

    def remove(self, gloss: str) -> int:
        """Delete every prototype of `gloss`; returns how many were removed."""
        keep = [i for i, g in enumerate(self.labels) if g != gloss]
        n = len(self.labels) - len(keep)
        self.Z = self.Z[keep]
        self.labels = [self.labels[i] for i in keep]
        return n

    def _fit_novelty(self, max_rows: int = 2000) -> None:
        """Nearest-other-clip similarity percentiles: below sim_lo confidence goes to 0, above sim_hi it is kept."""
        n = len(self.labels)
        if n < 3:
            self.sim_lo, self.sim_hi = -1.0, 0.0
            return
        rows = np.random.default_rng(0).choice(n, size=min(n, max_rows), replace=False)
        S = self.Z[rows] @ self.Z.T
        S[np.arange(len(rows)), rows] = -np.inf
        if self.mirror:  # a clip's own mirror is not a neighbour
            twin = np.where(rows % 2 == 0, rows + 1, rows - 1)
            S[np.arange(len(rows)), np.clip(twin, 0, n - 1)] = -np.inf
        nn = S.max(axis=1)
        nn = nn[np.isfinite(nn)]
        if nn.size == 0:
            self.sim_lo, self.sim_hi = -1.0, 0.0
            return
        self.sim_lo, self.sim_hi = float(np.percentile(nn, 1)) - 0.1, float(np.percentile(nn, 10))

    def calibrate(self, clips, labels, grid=(0.01, 0.02, 0.03, 0.05, 0.08, 0.12, 0.2, 0.3, 0.5)) -> float:
        """Pick the vote temperature with the lowest negative log-likelihood on held-out clips; returns it."""
        sims = [self._sims(xyz) for xyz in clips]
        best, best_nll = self.temperature, np.inf
        for t in grid:
            nll = 0.0
            for s, g in zip(sims, labels):
                nll -= np.log(max(self._vote(s, t).get(str(g), 0.0), 1e-6))
            if nll < best_nll:
                best, best_nll = t, nll
        self.temperature = float(best)
        return self.temperature

    # --- inference -------------------------------------------------------------------------------------------
    def _sims(self, xyz) -> np.ndarray:
        if self.mean is None:
            raise RuntimeError("classifier is not fitted")
        return self.Z @ self._embed(self._raw(xyz)[None])[0]

    def _vote(self, sims: np.ndarray, temperature: float) -> dict[str, float]:
        k = min(self.k * (2 if self.mirror else 1), len(sims))
        nn = np.argpartition(-sims, k - 1)[:k]
        w = np.exp((sims[nn] - sims[nn].max()) / max(temperature, 1e-6))
        votes: dict[str, float] = {}
        for i, wi in zip(nn, w):
            votes[self.labels[i]] = votes.get(self.labels[i], 0.0) + float(wi)
        total = sum(votes.values())
        return {g: v / total for g, v in votes.items()}

    def novelty(self, max_sim: float) -> float:
        span = max(self.sim_hi - self.sim_lo, 1e-6)
        return float(np.clip((max_sim - self.sim_lo) / span, 0.0, 1.0))

    def predict_proba(self, xyz) -> dict[str, float]:
        """Calibrated confidence per class (sums to <= 1; the rest is 'unknown'), every known class present."""
        sims = self._sims(xyz)
        scale = self.novelty(float(sims.max()))
        votes = self._vote(sims, self.temperature)
        return {g: votes.get(g, 0.0) * scale for g in self.classes}

    def predict(self, xyz, top: int = 3) -> list[tuple[str, float]]:
        """Top classes by confidence, best first: [(gloss, confidence), ...]."""
        p = self.predict_proba(xyz)
        return sorted(p.items(), key=lambda kv: -kv[1])[:top]

    # --- persistence -----------------------------------------------------------------------------------------
    def save(self, path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(path, Z=self.Z, labels=np.array(self.labels), mean=self.mean, std=self.std,
                            params=np.array([self.k, self.temperature, float(self.mirror), self.steps,
                                             self.sim_lo, self.sim_hi], dtype=np.float64))
        return path

    @classmethod
    def load(cls, path) -> "KNNClassifier":
        d = np.load(path, allow_pickle=False)
        k, t, m, steps, lo, hi = d["params"].tolist()
        obj = cls(k=int(k), temperature=t, mirror=bool(m), steps=int(steps))
        obj.Z, obj.labels, obj.mean, obj.std = d["Z"], [str(x) for x in d["labels"]], d["mean"], d["std"]
        obj.sim_lo, obj.sim_hi = lo, hi
        return obj
