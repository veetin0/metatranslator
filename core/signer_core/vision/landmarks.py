"""MediaPipe Holistic results -> the 75-point layout (the ONE conversion; every producer uses it).

Rows 0-32 = pose_landmarks, 33-53 = left_hand_landmarks, 54-74 = right_hand_landmarks, exactly as
MediaPipe labels them. No mirroring, no left/right swap (feed RGB, un-flipped frames; flipping is a
training augmentation only). x, y as returned (normalised image coords), z raw. A missing pose or hand
(None, empty, or wrong point count) is NaN in all of its rows. Face is not stored.
"""
from __future__ import annotations

import numpy as np

from ..contracts import LAYOUT, N_POINTS

_PARTS = (
    ("pose", "pose_landmarks"),
    ("left_hand", "left_hand_landmarks"),
    ("right_hand", "right_hand_landmarks"),
)


def _flat(lms):
    """Normalise a landmark container to a flat list of points, or [] if missing.

    Handles None, [], a plain list (Tasks), a nested [[...]] list (first person/hand) and legacy
    NormalizedLandmarkList objects (`.landmark`)."""
    if lms is None:
        return []
    if hasattr(lms, "landmark"):
        lms = lms.landmark
    lms = list(lms)
    if lms and not hasattr(lms[0], "x"):  # nested [[...]]
        lms = _flat(lms[0])
    return lms


def results_to_75(result) -> np.ndarray:
    """MediaPipe Tasks `HolisticLandmarkerResult` (or legacy solutions results) -> (75, 3) float32."""
    out = np.full((N_POINTS, 3), np.nan, dtype=np.float32)
    for name, key in _PARTS:
        rows = LAYOUT[name]
        pts = _flat(getattr(result, key, None))
        if len(pts) != len(rows):
            continue
        for row, p in zip(rows, pts):
            z = getattr(p, "z", None)
            out[row] = (p.x, p.y, np.nan if z is None else z)
    return out


result_to_frame = results_to_75  # alias (team convention)
