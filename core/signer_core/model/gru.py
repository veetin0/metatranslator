"""BiGRU sign classifier (trained by core/tools/train_gru.py) behind the same API as KNNClassifier.

Trained signs live in the network (PopSign plus taught glasses reps, `HELLO_G` counts as HELLO). Teach-a-sign at
runtime adds a sign the network has never seen to a small kNN on the side; reps of a sign the network knows are
already in it (retrain to fold new ones in).
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

from ..vision.features import FEATURE_DIM, clip_features
from .knn import KNNClassifier, trim_active


def make_model(n_cls: int, hidden: int = 128):
    import torch
    import torch.nn as nn

    class Net(nn.Module):
        def __init__(self):
            super().__init__()
            self.inp = nn.Sequential(nn.Linear(FEATURE_DIM, hidden), nn.GELU(), nn.Dropout(0.2))
            self.gru = nn.GRU(hidden, hidden, num_layers=2, batch_first=True, bidirectional=True, dropout=0.2)
            self.out = nn.Sequential(nn.Dropout(0.3), nn.Linear(4 * hidden, n_cls))

        def forward(self, x):
            h, _ = self.gru(self.inp(x))
            return self.out(torch.cat([h.mean(1), h.max(1).values], dim=1))

    return Net()


class GRUClassifier:
    name = "gru"

    def __init__(self, path):
        import torch

        ck = torch.load(path, map_location="cpu", weights_only=False)
        self.net = make_model(len(ck["classes"]))
        self.net.load_state_dict(ck["state"])
        self.net.eval()
        self.mean, self.std = ck["mean"], ck["std"]
        self._classes = list(ck["classes"])
        self._extra = KNNClassifier(mirror=True)  # taught signs the network does not know
        self._torch = torch

    @property
    def labels(self) -> list[str]:  # Teach reads this to see which reps are already loaded
        return list(self._extra.labels) + [f"{g}_G" for g in self._classes] + list(self._classes)

    @property
    def classes(self) -> list[str]:
        return sorted(set(self._classes) | set(self._extra.labels))

    def add(self, xyz, gloss: str) -> None:
        if gloss.removesuffix("_G") in self._classes:
            return
        self._extra.add(xyz, gloss)

    def remove(self, gloss: str) -> int:
        return self._extra.remove(gloss) if self._extra.labels else 0

    def _gru(self, xyz) -> np.ndarray:
        f = clip_features(trim_active(xyz)).astype(np.float32)
        x = self._torch.tensor(((f - self.mean) / self.std)[None], dtype=self._torch.float32)
        with self._torch.no_grad():
            return self._torch.softmax(self.net(x), dim=1)[0].numpy()

    def predict_proba(self, xyz) -> dict[str, float]:
        p = dict(zip(self._classes, self._gru(xyz).tolist()))
        if self._extra.labels:
            for g, c in self._extra.predict_proba(xyz).items():
                p[g] = max(p.get(g, 0.0), c)
        return p

    def predict(self, xyz, top: int = 3) -> list[tuple[str, float]]:
        return sorted(self.predict_proba(xyz).items(), key=lambda kv: -kv[1])[:top]
