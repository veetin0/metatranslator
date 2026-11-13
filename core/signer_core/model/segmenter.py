"""Streaming REST-based segmenter: hands up = signing, hands down or out of frame = REST (CONTRACTS §1).

A frame is "up" when a hand is detected and its wrist is above the rest line (the hips, or 2.2 shoulder widths
below the shoulders when the hips are not tracked). A segment starts after `on_frames` up frames and ends after
`gap_ms` without an up frame, or is cut at `max_ms`. Frames live in RAM only.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass

import numpy as np

from ..contracts import LEFT_HAND, RIGHT_HAND

L_SHOULDER, R_SHOULDER, L_HIP, R_HIP = 11, 12, 23, 24
WRISTS = (LEFT_HAND.start, RIGHT_HAND.start)


@dataclass
class Segment:
    xyz: np.ndarray  # (T, 75, 3) float32
    t_ms: np.ndarray  # (T,) int64
    start_ms: int
    end_ms: int

    @property
    def duration_ms(self) -> int:
        return self.end_ms - self.start_ms


def rest_line(frame: np.ndarray) -> float:
    """Image y (down = larger) below which a wrist counts as resting; +inf if the body is not tracked."""
    hips = frame[[L_HIP, R_HIP], 1]
    if np.isfinite(hips).all():
        return float(hips.mean())
    sh = frame[[L_SHOULDER, R_SHOULDER]]
    if np.isfinite(sh).all():
        width = float(np.linalg.norm(sh[0, :2] - sh[1, :2]))
        return float(sh[:, 1].mean()) + 2.2 * max(width, 1e-3)
    return float("inf")


def is_up(frame) -> bool:
    """True when a detected hand's wrist is above the rest line."""
    frame = np.asarray(frame, dtype=np.float32)
    line = rest_line(frame)
    for w in WRISTS:
        y = frame[w, 1]
        if np.isfinite(y) and y < line:
            return True
    return False


class Segmenter:
    """push(frame75, ts_ms) -> Segment | None; flush() -> Segment | None; reset()."""

    def __init__(self, on_frames: int = 2, gap_ms: int = 350, min_ms: int = 250, max_ms: int = 4000,
                 pre_roll: int = 3, min_frames: int = 4):
        self.on_frames, self.gap_ms, self.min_ms, self.max_ms = on_frames, gap_ms, min_ms, max_ms
        self.min_frames = min_frames
        self._pre: deque = deque(maxlen=max(pre_roll, on_frames))
        self.reset()

    def reset(self) -> None:
        self._pre.clear()
        self._frames: list[np.ndarray] = []
        self._ts: list[int] = []
        self._active = False
        self._run = 0
        self._last_up_i = -1
        self._last_up_ts = 0

    @property
    def active(self) -> bool:
        return self._active

    def push(self, frame, ts_ms: int) -> Segment | None:
        frame = np.asarray(frame, dtype=np.float32)
        if frame.shape != (75, 3):
            raise ValueError(f"frame must be (75, 3), got {frame.shape}")
        ts_ms = int(ts_ms)
        up = is_up(frame)
        if not self._active:
            self._pre.append((frame, ts_ms))
            self._run = self._run + 1 if up else 0
            if self._run >= self.on_frames:
                self._active = True
                self._frames = [f for f, _ in self._pre]
                self._ts = [t for _, t in self._pre]
                self._pre.clear()
                self._last_up_i, self._last_up_ts = len(self._frames) - 1, ts_ms
            return None

        if ts_ms - self._ts[0] > self.max_ms:  # cut before this frame so no segment is longer than max_ms
            seg = self._close(len(self._frames) - 1, post_roll=0)
            self.push(frame, ts_ms)
            return seg
        self._frames.append(frame)
        self._ts.append(ts_ms)
        if up:
            self._last_up_i, self._last_up_ts = len(self._frames) - 1, ts_ms
        if not up and ts_ms - self._last_up_ts >= self.gap_ms:
            return self._close(self._last_up_i)
        return None

    def flush(self) -> Segment | None:
        """End the open segment now (e.g. on Stop); None if nothing worth classifying."""
        if not self._active:
            self.reset()
            return None
        return self._close(self._last_up_i)

    def _close(self, last: int, post_roll: int = 1) -> Segment | None:
        frames, ts = self._frames[: last + 1 + post_roll], self._ts[: last + 1 + post_roll]
        self.reset()
        if len(frames) < self.min_frames or ts[-1] - ts[0] < self.min_ms:
            return None
        return Segment(np.stack(frames), np.asarray(ts, dtype=np.int64), ts[0], ts[-1])
