"""Question flag from face blendshapes (live only; the face is never stored, CONTRACTS §5).

ASL marks questions on the face: raised brows for yes/no questions, furrowed brows (often with a head tilt) for
wh-questions. During one signed segment we average the brow blendshapes over the frames where a face was found;
if raised or furrowed brows hold for enough of the segment, the caption is flagged as a question.

Blendshape names are MediaPipe's (browInnerUp, browOuterUpLeft/Right, browDownLeft/Right). Holistic must be
created with `output_face_blendshapes=True` for `blendshapes_from_result` to return anything; until then the
detector simply has no vote (None) and the template decides.

    det = QuestionDetector()
    for raw in results_of_segment: det.push(blendshapes_from_result(raw))
    det.decide()   # True / False / None (no face seen)
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

RAISE_KEYS = ("browInnerUp", "browOuterUpLeft", "browOuterUpRight")
FURROW_KEYS = ("browDownLeft", "browDownRight")


def _mean(bs: Mapping[str, float], keys: Iterable[str]) -> float:
    vals = [float(bs[k]) for k in keys if k in bs]
    return sum(vals) / len(vals) if vals else 0.0


def brow_scores(bs: Mapping[str, float]) -> tuple[float, float]:
    """(raise, furrow) in [0, 1] for one frame."""
    return _mean(bs, RAISE_KEYS), _mean(bs, FURROW_KEYS)


def blendshapes_from_result(raw: Any) -> dict[str, float] | None:
    """MediaPipe Holistic/FaceLandmarker result -> {name: score}, or None when there is no face / no blendshapes."""
    cats = getattr(raw, "face_blendshapes", None)
    if not cats:
        return None
    # FaceLandmarker returns a list per face; Holistic returns one flat list of categories.
    first = cats[0]
    if isinstance(first, (list, tuple)):
        cats = first
    out = {}
    for c in cats:
        name = getattr(c, "category_name", None)
        if name:
            out[name] = float(getattr(c, "score", 0.0))
    return out or None


@dataclass
class QuestionDetector:
    raise_thr: float = 0.45
    furrow_thr: float = 0.45
    min_fraction: float = 0.4  # share of face frames in the segment that must show the marker
    min_frames: int = 3
    _n: int = field(default=0, init=False)
    _raised: int = field(default=0, init=False)
    _furrowed: int = field(default=0, init=False)

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "QuestionDetector":
        env = os.environ if env is None else env
        return cls(raise_thr=float(env.get("SIGNER_Q_RAISE", 0.45)),
                   furrow_thr=float(env.get("SIGNER_Q_FURROW", 0.45)))

    def push(self, bs: Mapping[str, float] | None) -> None:
        if not bs:
            return
        r, f = brow_scores(bs)
        self._n += 1
        self._raised += r >= self.raise_thr
        self._furrowed += f >= self.furrow_thr

    def kind(self) -> str | None:
        """'yes_no' (raised), 'wh' (furrowed), 'none', or None when too few face frames were seen."""
        if self._n < self.min_frames:
            return None
        rf, ff = self._raised / self._n, self._furrowed / self._n
        if max(rf, ff) < self.min_fraction:
            return "none"
        return "yes_no" if rf >= ff else "wh"

    def decide(self) -> bool | None:
        k = self.kind()
        return None if k is None else k != "none"

    def reset(self) -> None:
        self._n = self._raised = self._furrowed = 0


def question_enabled(env: Mapping[str, str] | None = None) -> bool:
    """The question graft is behind SIGNER_FLAGS=question."""
    env = os.environ if env is None else env
    return "question" in {f.strip().lower() for f in env.get("SIGNER_FLAGS", "").split(",")}
