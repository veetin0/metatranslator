"""Segmenter + classifier -> one Prediction per signed segment, with tier and top-2 (contracts.tier_for)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field

from ..contracts import REST, tier_for
from .data import load_dataset, read_vocab
from .knn import KNNClassifier
from .segmenter import Segment, Segmenter


@dataclass
class Prediction:
    gloss: str
    confidence: float
    tier: str  # contracts.Tier
    top: list = field(default_factory=list)  # [(gloss, confidence), ...] best first, top[0] is the prediction
    start_ms: int = 0
    end_ms: int = 0

    @property
    def alternatives(self) -> list[tuple[str, float]]:
        """Runner-ups (top-2 alternative for the 'unsure' tier), REST excluded."""
        return [(g, c) for g, c in self.top[1:] if g != REST][:2]

    @property
    def is_rest(self) -> bool:
        return self.gloss == REST


def classify(classifier, xyz, top: int = 3) -> Prediction:
    ranked = classifier.predict(xyz, top=top)
    gloss, conf = ranked[0] if ranked else (REST, 0.0)
    return Prediction(gloss, float(conf), tier_for(conf), [(g, float(c)) for g, c in ranked])


class Recognizer:
    """push(frame75, ts_ms) -> Prediction | None (REST segments are dropped); flush() on Stop."""

    def __init__(self, classifier, segmenter: Segmenter | None = None):
        self.classifier = classifier
        self.segmenter = segmenter or Segmenter()

    def _on_segment(self, seg: Segment | None) -> Prediction | None:
        if seg is None:
            return None
        p = classify(self.classifier, seg.xyz)
        p.start_ms, p.end_ms = seg.start_ms, seg.end_ms
        return None if p.is_rest else p

    def push(self, frame, ts_ms: int) -> Prediction | None:
        return self._on_segment(self.segmenter.push(frame, ts_ms))

    def flush(self) -> Prediction | None:
        return self._on_segment(self.segmenter.flush())

    def reset(self) -> None:
        self.segmenter.reset()


def build_classifier(data_dir: str | None = None, sources=("own", "popsign"), **knn_kwargs) -> KNNClassifier:
    """Fit the kNN on every clip of `sources` under SIGNER_DATA_DIR (default data/), vocabulary glosses only."""
    data_dir = data_dir or os.environ.get("SIGNER_DATA_DIR", "data")
    gru = os.path.join(data_dir, "models", "gru.pt")
    large = os.path.join(data_dir, "models", "gru_large.pt")  # ~600 glosses, core/tools/train_large.py
    if os.path.exists(large) and os.environ.get("SIGNER_MODEL") == "gru_large":
        from .gru import GRUClassifier

        return GRUClassifier(large)
    if os.path.exists(gru) and os.environ.get("SIGNER_MODEL", "gru") == "gru":  # trained by core/tools/train_gru.py
        from .gru import GRUClassifier

        return GRUClassifier(gru)
    vocab_path = os.path.join(data_dir, "VOCAB.md")
    vocab = read_vocab(vocab_path) if os.path.exists(vocab_path) else None
    ds = load_dataset(data_dir, sources, vocab=vocab)
    if not len(ds):
        raise FileNotFoundError(f"no landmark clips for {list(sources)} under {data_dir}/")
    return KNNClassifier(**knn_kwargs).fit(ds.xyz, ds.gloss)
