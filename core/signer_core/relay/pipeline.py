"""Frame -> landmarks -> Recognizer -> phrase -> caption events (CONTRACTS §1, §4). Frames stay in RAM.

Signs are grouped into a phrase until the hands have rested for `phrase_gap_ms` (or `max_signs` is reached),
then one `caption` is emitted: text from the template, confidence = the weakest kept sign, tier from
`contracts.tier_for`, alternatives = the weakest sign swapped for its runner-ups. Signs below the `unsure`
threshold are left out of the phrase; a phrase with none left becomes the `none` caption ("Didn't catch that").
Each recognised sign also emits a `partial` (card live hint).
"""
from __future__ import annotations

import threading

from ..contracts import NONE_TEXT, REST, tier_for
from ..language import ENGLISH, to_english
from ..model import Prediction, Recognizer
from .session import now_ms


class JpegLandmarker:
    """JPEG bytes + frame header -> (75, 3) landmarks via MediaPipe Holistic (lazy: cv2/mediapipe on first use)."""

    ROT = {90: "ROTATE_90_CLOCKWISE", 180: "ROTATE_180", 270: "ROTATE_90_COUNTERCLOCKWISE"}

    def __init__(self, model=None):
        self._model = model
        self._h = None

    def __call__(self, jpeg: bytes, header: dict):
        import cv2
        import numpy as np

        frame = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
        if frame is None:
            raise ValueError("frame is not a decodable JPEG")
        rot = int(header.get("rot", 0) or 0) % 360
        if rot in self.ROT:
            frame = cv2.rotate(frame, getattr(cv2, self.ROT[rot]))
        return self.landmarks(frame, int(header.get("ts_ms", 0)))

    def landmarks(self, frame_bgr, ts_ms: int):
        if self._h is None:
            from ..vision import Holistic

            self._h = Holistic(self._model).open()
        f75, _raw = self._h.process(frame_bgr, ts_ms, bgr=True)
        return f75

    def close(self):
        if self._h is not None:
            self._h.close()
            self._h = None


class PhraseBuilder:
    def __init__(self, english: dict[str, str] | None = None, gap_ms: int = 1200, max_signs: int = 6):
        self.english = english or ENGLISH
        self.gap_ms, self.max_signs = gap_ms, max_signs
        self._preds: list[Prediction] = []
        self._n = 0

    @property
    def pending(self) -> bool:
        return bool(self._preds)

    def add(self, pred: Prediction) -> dict | None:
        self._preds.append(pred)
        return self.flush() if len(self._preds) >= self.max_signs else None

    def tick(self, ts_ms: int) -> dict | None:
        if self._preds and ts_ms - self._preds[-1].end_ms >= self.gap_ms:
            return self.flush()
        return None

    def flush(self) -> dict | None:
        preds, self._preds = self._preds, []
        if not preds:
            return None
        self._n += 1
        return self.caption(preds, f"c{self._n}")

    def reset(self) -> None:
        self._preds = []

    def caption(self, preds: list[Prediction], cid: str) -> dict:
        kept = [p for p in preds if p.tier != "none"]
        if not kept:
            conf = max(p.confidence for p in preds)
            return {"type": "caption", "id": cid, "text": NONE_TEXT, "gloss": [], "tier": "none",
                    "confidence": round(conf, 3), "alternatives": [], "question": False, "mode": "template",
                    "speak": False, "ts": now_ms()}
        gloss = [p.gloss for p in kept]
        confs = [p.confidence for p in kept]
        conf = min(confs)
        tier = tier_for(conf)
        text, question = to_english(gloss, self.english)
        weakest = confs.index(conf)
        others = min((c for i, c in enumerate(confs) if i != weakest), default=1.0)
        alternatives = []
        for g, c in kept[weakest].alternatives:
            alt = gloss[:weakest] + [g] + gloss[weakest + 1:]
            alt_text, _ = to_english(alt, self.english)
            if alt_text and alt_text != text:
                alternatives.append({"text": alt_text, "gloss": alt, "confidence": round(min(c, others), 3)})
        return {"type": "caption", "id": cid, "text": text, "gloss": gloss, "tier": tier,
                "confidence": round(conf, 3), "alternatives": alternatives[:2], "question": bool(question),
                "mode": "template", "speak": tier == "confirmed", "ts": now_ms()}


class Pipeline:
    """Thread-safe: push_jpeg / push_landmarks -> list of events to broadcast (partial, caption)."""

    def __init__(self, classifier=None, landmarker=None, english: dict[str, str] | None = None,
                 phrase_gap_ms: int = 1200, on_segment=None):
        self.classifier = classifier
        self.recognizer = Recognizer(classifier) if classifier is not None else None
        self.landmarker = landmarker or JpegLandmarker()
        self.phrases = PhraseBuilder(english, gap_ms=phrase_gap_ms)
        self.on_segment = on_segment  # called on every recognised segment (session idle timer)
        self._lock = threading.Lock()
        self.frames = 0

    def set_classifier(self, classifier) -> None:
        with self._lock:
            self.classifier = classifier
            self.recognizer = Recognizer(classifier)

    def push_jpeg(self, header: dict, jpeg: bytes) -> list[dict]:
        f75 = self.landmarker(jpeg, header)
        return self.push_landmarks(f75, int(header.get("ts_ms", 0)))

    def push_landmarks(self, f75, ts_ms: int) -> list[dict]:
        with self._lock:
            self.frames += 1
            if self.recognizer is None:
                return []
            out = []
            pred = self.recognizer.push(f75, ts_ms)
            if pred is not None:
                out += self._on_pred(pred)
            # the phrase only closes on rest: a sign in progress belongs to it
            cap = None if self.recognizer.segmenter.active else self.phrases.tick(ts_ms)
            return out + ([cap] if cap else [])

    def _on_pred(self, pred: Prediction) -> list[dict]:
        if self.on_segment:
            self.on_segment()
        if pred.gloss == REST:
            return []
        out = [{"type": "partial", "gloss": pred.gloss, "confidence": round(pred.confidence, 3), "ts": now_ms()}]
        cap = self.phrases.add(pred)
        return out + ([cap] if cap else [])

    def flush(self) -> list[dict]:
        """End the open sign and phrase now (e.g. producer disconnected)."""
        with self._lock:
            out = []
            if self.recognizer is not None:
                pred = self.recognizer.flush()
                if pred is not None:
                    out += self._on_pred(pred)
            cap = self.phrases.flush()
            return out + ([cap] if cap else [])

    def reset(self) -> None:
        """Drop everything in flight (Stop: consent withdrawn, nothing more is emitted)."""
        with self._lock:
            if self.recognizer is not None:
                self.recognizer.reset()
            self.phrases.reset()
