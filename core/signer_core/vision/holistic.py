"""MediaPipe Tasks HolisticLandmarker wrapper (mediapipe 1.2.x has no mp.solutions).

    with Holistic() as h:
        frame75, raw = h.process(frame_bgr, ts_ms)        # (75,3) float32, HolisticLandmarkerResult

RunningMode.VIDEO, model `holistic_landmarker.task` (float16), min_pose_detection_confidence=0.5,
min_hand_landmarks_confidence=0.5, no face blendshapes. Create a NEW Holistic per clip / per stream: it
tracks across frames, so state must not leak between unrelated videos. Timestamps passed to `process`
must be strictly increasing; a non-increasing value is bumped to last+1 (MediaPipe would raise).
"""
from __future__ import annotations

import os
import urllib.request
from pathlib import Path

from .landmarks import results_to_75

MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/holistic_landmarker/holistic_landmarker/float16/latest/"
    "holistic_landmarker.task"
)
MODEL_NAME = "holistic_landmarker.task"
MIN_MODEL_BYTES = 1_000_000  # a truncated / error-page download is far smaller than the ~13 MB model


def model_path() -> Path:
    """$SIGNER_HOLISTIC_MODEL, else ~/.cache/signer_core/holistic_landmarker.task."""
    env = os.environ.get("SIGNER_HOLISTIC_MODEL")
    return Path(env).expanduser() if env else Path.home() / ".cache" / "signer_core" / MODEL_NAME


def ensure_model(path=None) -> Path:
    """Return the local model path, downloading it once (atomic) if it is missing."""
    p = Path(path).expanduser() if path else model_path()
    if p.exists() and p.stat().st_size >= MIN_MODEL_BYTES:
        return p
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".part")
    try:
        urllib.request.urlretrieve(MODEL_URL, tmp)
        if tmp.stat().st_size < MIN_MODEL_BYTES:
            raise OSError(f"downloaded model too small ({tmp.stat().st_size} bytes) from {MODEL_URL}")
        os.replace(tmp, p)
    finally:
        if tmp.exists():
            tmp.unlink()
    return p


class Holistic:
    def __init__(self, model=None):
        self._model = model
        self._h = None
        self._last_ts = -1

    def open(self):
        if self._h is not None:
            return self
        import mediapipe as mp  # noqa: F401  (lazy: keeps `import signer_core.vision` numpy-only)
        from mediapipe.tasks.python import BaseOptions
        from mediapipe.tasks.python import vision as mp_vision

        opts = mp_vision.HolisticLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=str(ensure_model(self._model))),
            running_mode=mp_vision.RunningMode.VIDEO,
            min_pose_detection_confidence=0.5,
            min_hand_landmarks_confidence=0.5,
            output_face_blendshapes=False,
        )
        self._h = mp_vision.HolisticLandmarker.create_from_options(opts)
        self._last_ts = -1
        return self

    def close(self):
        if self._h is not None:
            self._h.close()
            self._h = None

    def __enter__(self):
        return self.open()

    def __exit__(self, *exc):
        self.close()
        return False

    def process(self, frame, ts_ms, bgr=True):
        """frame: uint8 (H, W, 3), BGR if `bgr` (OpenCV) else RGB. Not mirrored. Returns (frame75, raw)."""
        if self._h is None:
            self.open()
        import mediapipe as mp
        import numpy as np

        arr = np.asarray(frame)
        if arr.ndim != 3 or arr.shape[2] != 3 or arr.dtype != np.uint8:
            raise ValueError(f"frame must be uint8 (H, W, 3), got {arr.dtype} {arr.shape}")
        rgb = np.ascontiguousarray(arr[:, :, ::-1] if bgr else arr)
        ts = max(int(ts_ms), self._last_ts + 1)
        self._last_ts = ts
        raw = self._h.detect_for_video(mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb), ts)
        return results_to_75(raw), raw
