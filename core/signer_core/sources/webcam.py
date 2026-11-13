"""Webcam frame source + Holistic bench.

    python -m signer_core.sources.webcam --bench 10 --out .hackforge/evidence/M0-bench.json
    python -m signer_core.sources.webcam --bench 3 --dry-run        # synthetic frames, writes nothing

The bench runs the real `signer_core.vision.Holistic` over live webcam frames for N seconds. Frames are
processed in RAM and dropped (never written to disk). `--out` is only ever written from a real webcam run
that processed at least one frame: with `--dry-run` (synthetic frames) or a camera that cannot be opened,
nothing is written and the exit code is non-zero (dry-run: 0, it only prints).

Only the stdlib is imported at module level; numpy / cv2 / mediapipe are imported lazily so that
`import signer_core.sources.webcam` works anywhere.
"""
from __future__ import annotations

import argparse
import datetime
import json
import platform
import sys
import time
from pathlib import Path


class CameraError(RuntimeError):
    pass


class WebcamSource:
    """OpenCV webcam. Iterating yields (frame_bgr uint8 (H, W, 3), ts_ms) with ts_ms strictly increasing
    (milliseconds since open). Frames are NOT mirrored. Use as a context manager."""

    def __init__(self, index: int = 0, width: int | None = None, height: int | None = None,
                 fps: float | None = None, first_frame_timeout_s: float = 10.0):
        self.index, self.width, self.height, self.fps = index, width, height, fps
        self.first_frame_timeout_s = first_frame_timeout_s
        self._cap = None
        self._t0 = 0.0
        self._last_ts = -1

    def open(self):
        import cv2

        cap = cv2.VideoCapture(self.index)
        if not cap.isOpened():
            cap.release()
            raise CameraError(
                f"cannot open camera {self.index} (macOS: allow Camera for your terminal in "
                "System Settings > Privacy & Security > Camera, then restart the terminal)"
            )
        if self.width:
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        if self.height:
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        if self.fps:
            cap.set(cv2.CAP_PROP_FPS, self.fps)
        self._cap = cap
        deadline = time.monotonic() + self.first_frame_timeout_s
        while True:  # the first frame can take seconds (permission prompt, auto-exposure)
            ok, frame = cap.read()
            if ok and frame is not None:
                self._pending = frame
                break
            if time.monotonic() > deadline:
                self.close()
                raise CameraError(
                    f"camera {self.index} opened but delivered no frame in {self.first_frame_timeout_s:.0f}s "
                    "(permission denied or camera busy)"
                )
        self._t0 = time.monotonic()
        return self

    def close(self):
        if self._cap is not None:
            self._cap.release()
            self._cap = None

    def __enter__(self):
        return self.open()

    def __exit__(self, *exc):
        self.close()
        return False

    @property
    def resolution(self):
        import cv2

        return [int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT))]

    @property
    def reported_fps(self) -> float:
        import cv2

        return float(self._cap.get(cv2.CAP_PROP_FPS) or 0.0)

    def read(self):
        """Next (frame_bgr, ts_ms), or None if the camera stopped delivering."""
        if self._cap is None:
            raise CameraError("camera is not open")
        if getattr(self, "_pending", None) is not None:
            frame, self._pending = self._pending, None
        else:
            ok, frame = self._cap.read()
            if not ok or frame is None:
                return None
        ts = max(int((time.monotonic() - self._t0) * 1000), self._last_ts + 1)
        self._last_ts = ts
        return frame, ts

    def __iter__(self):
        while True:
            item = self.read()
            if item is None:
                return
            yield item


class SyntheticSource:
    """Moving-noise frames (no camera needed); same interface as WebcamSource. For --dry-run and tests."""

    def __init__(self, width=640, height=480, fps=30.0):
        self.width, self.height, self.fps = width, height, fps
        self._i = 0
        self.resolution = [width, height]
        self.reported_fps = float(fps)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        import numpy as np

        rng = np.random.default_rng(self._i)
        frame = rng.integers(0, 255, (self.height, self.width, 3), dtype=np.uint8)
        ts = int(self._i * 1000 / self.fps)
        self._i += 1
        return frame, ts

    def __iter__(self):
        while True:
            yield self.read()


def run_bench(source, seconds: float, model=None, warmup_frames: int = 5) -> dict:
    """Run Holistic over `source` for `seconds` of wall time (after the model is loaded and `warmup_frames`
    are discarded). Returns the stats dict (without machine / date / source fields)."""
    import numpy as np

    from signer_core.vision import Holistic

    frames = pose_frames = hand_frames = 0
    lat_ms = []
    with Holistic(model) as h, source as src:
        for n, (frame, ts) in enumerate(src):
            t0 = time.perf_counter()
            f75, _raw = h.process(frame, ts, bgr=True)
            dt = time.perf_counter() - t0
            if n < warmup_frames:
                if n == warmup_frames - 1:
                    start = time.perf_counter()
                continue
            frames += 1
            lat_ms.append(dt * 1000)
            pose_frames += bool(~np.isnan(f75[:33, 0]).all())
            hand_frames += bool(~np.isnan(f75[33:, 0]).all())
            if time.perf_counter() - start >= seconds:
                break
        elapsed = time.perf_counter() - start if frames else 0.0
        resolution, reported = list(src.resolution), src.reported_fps
    if not frames:
        raise CameraError("no frames processed")
    lat = np.asarray(lat_ms)
    return {
        "fps": round(frames / elapsed, 2),
        "frames": frames,
        "seconds": round(elapsed, 2),
        "hand_frames_pct": round(100.0 * hand_frames / frames, 1),
        "pose_frames_pct": round(100.0 * pose_frames / frames, 1),
        "latency_ms_p50": round(float(np.percentile(lat, 50)), 1),
        "latency_ms_p95": round(float(np.percentile(lat, 95)), 1),
        "camera_reported_fps": round(reported, 1),
        "resolution": resolution,
    }


def _versions() -> dict:
    out = {"python": platform.python_version()}
    try:
        import mediapipe

        out["mediapipe"] = mediapipe.__version__
    except ImportError:
        out["mediapipe"] = None
    try:
        import cv2

        out["opencv"] = cv2.__version__
    except ImportError:
        out["opencv"] = None
    return out


def build_parser():
    ap = argparse.ArgumentParser(description="Webcam source and MediaPipe Holistic benchmark.")
    ap.add_argument("--bench", type=float, metavar="SECONDS", required=True, help="run Holistic for N seconds")
    ap.add_argument("--out", help="write the result JSON here (real webcam runs only)")
    ap.add_argument("--camera", type=int, default=0, help="camera index (default 0)")
    ap.add_argument("--width", type=int, help="requested capture width")
    ap.add_argument("--height", type=int, help="requested capture height")
    ap.add_argument("--dry-run", action="store_true", help="synthetic frames instead of a camera; never writes --out")
    return ap


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    if args.bench <= 0:
        print("error: --bench must be > 0", file=sys.stderr)
        return 2
    source = SyntheticSource() if args.dry_run else WebcamSource(args.camera, args.width, args.height)
    try:
        stats = run_bench(source, args.bench)
    except CameraError as e:
        print(f"error: {e}", file=sys.stderr)
        return 3
    result = {
        **stats,
        "source": "synthetic" if args.dry_run else "webcam",
        "machine": f"{platform.node()} {platform.platform()} {platform.machine()}",
        **_versions(),
        "date": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
    }
    print(json.dumps(result, indent=2))
    if args.out and args.dry_run:
        print("dry-run: not writing --out (the evidence file only comes from a real webcam run)", file=sys.stderr)
    elif args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
