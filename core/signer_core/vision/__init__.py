"""Vision: MediaPipe Holistic -> 75-point landmarks (CONTRACTS.md section 5).

Importing this package needs only numpy: `Holistic` (mediapipe / cv2) is loaded lazily on first access.
"""
from __future__ import annotations

from .clip import load_clip, save_clip, validate_clip
from .features import clip_features, flat_features, frame_features
from .landmarks import result_to_frame, results_to_75

__all__ = [
    "Holistic", "clip_features", "ensure_model", "flat_features", "frame_features", "load_clip", "result_to_frame", "results_to_75", "save_clip", "validate_clip",
]


def __getattr__(name):  # lazy: keeps `import signer_core.vision` free of mediapipe / cv2
    if name in ("Holistic", "ensure_model", "model_path"):
        from . import holistic

        return getattr(holistic, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
