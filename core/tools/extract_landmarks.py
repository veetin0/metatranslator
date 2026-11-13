#!/usr/bin/env python
"""Batch landmark extractor: PopSign videos -> 75-point landmark clips (.npz), then delete the videos.

Output (CONTRACTS.md section 5): data/popsign/landmarks/<GLOSS>/<clip_id>.npz with keys
  xyz float16 (T,75,3) | t_ms int64 (T,) | fps float32 | gloss str | signer str | source str ('popsign')

LANDMARK CONVENTION (shared by every producer: PopSign, own webcam clips, glasses, live relay):
  Input is RGB, NOT mirrored, NOT flipped (flipping is training augmentation only).
  Row layout (signer_core.contracts.LAYOUT), always as MediaPipe labels the results:
    rows  0-32  = results.pose_landmarks          (33 points)
    rows 33-53  = results.left_hand_landmarks     (21 points)
    rows 54-74  = results.right_hand_landmarks    (21 points)
  No left/right swapping. x, y as returned (normalised image coords), z raw. A missing pose or
  hand (None / empty) is NaN in all of its rows. Face is not stored.
  `results_to_75` below accepts the MediaPipe Tasks HolisticLandmarkerResult (landmark lists, possibly
  nested [[...]]) and legacy mp.solutions.holistic results (objects with `.landmark`).

Backends (first available wins; see choose_backend):
  1. signer_core.vision.holistic.Holistic   (M0.3 crew, preferred)
  2. mediapipe Tasks HolisticLandmarker, RunningMode.VIDEO, holistic_landmarker.task (float16),
     min_pose_detection_confidence=0.5, min_hand_landmarks_confidence=0.5, no blendshapes.
     Model: $SIGNER_HOLISTIC_MODEL, else ~/.cache/signer_core/holistic_landmarker.task (downloaded if absent).
  3. legacy mp.solutions.holistic (only if this mediapipe still ships it)
A NEW Holistic is created for every clip, fed that clip's own strictly increasing timestamps
(frame_idx * 1000 / fps).

Privacy (R3): only landmark coordinates are stored. Source videos are deleted after the npz is
reloaded and verified (unless --keep-videos). Clips with no pose or unreadable video are logged and
their videos are kept so they can be inspected or retried.

Only the stdlib is imported at module level so `--help` works anywhere; numpy / cv2 / mediapipe are
imported lazily.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import time
from collections import namedtuple
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # repo root
CORE = Path(__file__).resolve().parents[1]  # core/
TOOLS = Path(__file__).resolve().parent
for _p in (str(CORE), str(TOOLS)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from signer_core.contracts import CLIP_KEYS, LAYOUT, N_POINTS  # noqa: E402  (stdlib only)

POSE_N = len(LAYOUT["pose"])
HAND_N = len(LAYOUT["left_hand"])
VIDEO_EXTS = {".mp4", ".mov", ".m4v", ".webm", ".avi", ".mkv"}
MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/holistic_landmarker/holistic_landmarker/float16/latest/"
    "holistic_landmarker.task"
)
DEFAULT_IN = ROOT / "data" / "popsign" / "raw"
DEFAULT_VOCAB = ROOT / "data" / "VOCAB.md"
DEFAULT_OUT = ROOT / "data" / "popsign" / "landmarks"

VocabRow = namedtuple("VocabRow", "gloss english source popsign_name")


# --------------------------------------------------------------------------------------------
# Landmark conversion (the one implementation; record.py imports it)
# --------------------------------------------------------------------------------------------
def _flat(lms):
    """Normalise a landmark container to a flat list of points, or [] if missing.

    Handles None, [], a plain list, a nested [[...]] list (first person/hand), and legacy
    NormalizedLandmarkList objects (`.landmark`)."""
    if lms is None:
        return []
    if hasattr(lms, "landmark"):
        lms = lms.landmark
    lms = list(lms)
    if lms and not hasattr(lms[0], "x"):  # nested [[...]]
        lms = _flat(lms[0])
    return lms


def results_to_75(results):
    """MediaPipe holistic results -> np.ndarray (75, 3) float32.

    Rows 0-32 pose_landmarks, 33-53 left_hand_landmarks, 54-74 right_hand_landmarks, exactly as
    MediaPipe labels them (no mirroring, no left/right swap; feed RGB, un-flipped frames). x, y as
    returned, z raw; a missing pose or hand (None, empty, or wrong point count) is NaN."""
    import numpy as np

    out = np.full((N_POINTS, 3), np.nan, dtype=np.float32)
    for name, key in (("pose", "pose_landmarks"), ("left_hand", "left_hand_landmarks"), ("right_hand", "right_hand_landmarks")):
        rows = LAYOUT[name]
        pts = _flat(getattr(results, key, None))
        if len(pts) != len(rows):
            continue
        for row, p in zip(rows, pts):
            z = getattr(p, "z", None)
            out[row] = (p.x, p.y, np.nan if z is None else z)
    return out


def resolve_results_to_75():
    """Prefer signer_core.vision's converter (M0.3) when importable, else the local one."""
    for modname in ("signer_core.vision.landmarks", "signer_core.vision"):
        try:
            mod = __import__(modname, fromlist=["results_to_75"])
            fn = getattr(mod, "results_to_75", None)
            if callable(fn):
                return fn
        except Exception:
            continue
    return results_to_75


# --------------------------------------------------------------------------------------------
# Clip IO
# --------------------------------------------------------------------------------------------
def _vision_attr(modname, attr):
    try:
        mod = __import__(modname, fromlist=[attr])
        fn = getattr(mod, attr, None)
        return fn if callable(fn) else None
    except Exception:
        return None


def write_clip(path, xyz, t_ms, fps, gloss, signer, source):
    """Write one landmark clip (CONTRACTS section 5). Atomic: written to <name>.tmp.npz, then renamed,
    so a crash never leaves a half-written file that a resumed run would treat as done.
    Uses signer_core.vision.clip.save_clip when available, else np.savez_compressed."""
    import numpy as np

    path = Path(path)
    xyz = np.asarray(xyz)
    if xyz.ndim != 3 or xyz.shape[1:] != (N_POINTS, 3):
        raise ValueError(f"xyz must be (T,{N_POINTS},3), got {xyz.shape}")
    t_ms = np.asarray(t_ms, dtype=np.int64)
    if t_ms.shape != (xyz.shape[0],):
        raise ValueError(f"t_ms must be ({xyz.shape[0]},), got {t_ms.shape}")
    xyz = xyz.astype(np.float16)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.stem + ".tmp.npz")
    saver = _vision_attr("signer_core.vision.clip", "save_clip")
    try:
        if saver is not None:
            saver(tmp, xyz, t_ms, float(fps), str(gloss), str(signer), str(source))
        else:
            np.savez_compressed(
                tmp, xyz=xyz, t_ms=t_ms, fps=np.float32(fps), gloss=np.array(str(gloss)),
                signer=np.array(str(signer)), source=np.array(str(source)),
            )
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()
    return path


def verify_clip(path, n_frames=None, gloss=None, source=None):
    """Reload an npz and check keys, dtypes and shapes. Raises ValueError on any problem."""
    import numpy as np

    with np.load(path, allow_pickle=False) as z:
        keys = set(z.files)
        if keys != set(CLIP_KEYS):
            raise ValueError(f"keys {sorted(keys)} != {sorted(CLIP_KEYS)}")
        xyz, t_ms, fps = z["xyz"], z["t_ms"], z["fps"]
        g, s, src = str(z["gloss"]), str(z["signer"]), str(z["source"])
    if xyz.dtype != np.float16 or xyz.ndim != 3 or xyz.shape[1:] != (N_POINTS, 3) or xyz.shape[0] < 1:
        raise ValueError(f"bad xyz {xyz.dtype} {xyz.shape}")
    if t_ms.dtype != np.int64 or t_ms.shape != (xyz.shape[0],):
        raise ValueError(f"bad t_ms {t_ms.dtype} {t_ms.shape}")
    if fps.dtype != np.float32 or fps.shape != () or not float(fps) > 0:
        raise ValueError(f"bad fps {fps.dtype} {fps.shape}")
    if n_frames is not None and xyz.shape[0] != n_frames:
        raise ValueError(f"T={xyz.shape[0]} expected {n_frames}")
    if gloss is not None and g != gloss:
        raise ValueError(f"gloss {g!r} != {gloss!r}")
    if source is not None and src != source:
        raise ValueError(f"source {src!r} != {source!r}")
    if not s:
        raise ValueError("empty signer")
    validator = _vision_attr("signer_core.vision.clip", "validate_clip")
    if validator is not None:
        try:
            if validator(path) is False:
                raise ValueError("signer_core.vision.clip.validate_clip rejected the file")
        except ValueError:
            raise
        except Exception as e:  # validate_clip raising = invalid
            raise ValueError(f"validate_clip: {e}") from e
    return xyz.shape[0]


# --------------------------------------------------------------------------------------------
# Holistic backends
# --------------------------------------------------------------------------------------------
def model_path():
    env = os.environ.get("SIGNER_HOLISTIC_MODEL")
    return Path(env).expanduser() if env else Path.home() / ".cache" / "signer_core" / "holistic_landmarker.task"


def ensure_model():
    """Return the local path of holistic_landmarker.task, downloading it once if needed."""
    p = model_path()
    if p.exists() and p.stat().st_size > 0:
        return p
    import urllib.request

    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".part")
    print(f"downloading Holistic model -> {p}", flush=True)
    urllib.request.urlretrieve(MODEL_URL, tmp)
    os.replace(tmp, p)
    return p


def choose_backend(prefer="auto"):
    """Return (backend, model_path_or_None). Done once in the parent so workers don't race."""
    if prefer == "auto" and _vision_attr("signer_core.vision.holistic", "Holistic") is not None:
        return "vision", None
    try:
        from mediapipe.tasks.python import vision as mp_vision  # noqa: F401

        if hasattr(mp_vision, "HolisticLandmarker"):
            return "tasks", str(ensure_model())
    except ImportError:
        pass
    try:
        import mediapipe as mp

        if hasattr(mp, "solutions") and hasattr(mp.solutions, "holistic"):
            return "legacy", None
    except ImportError:
        pass
    raise RuntimeError(
        "no Holistic backend: install mediapipe (python 3.12 venv: `python -m pip install -e \"core[dev]\"`)"
    )


class HolisticRunner:
    """One Holistic instance: process_bgr(frame_bgr, ts_ms) -> (75,3) float32. Use as a context manager.

    ts_ms must increase strictly across calls on the same runner; create a new runner per clip."""

    def __init__(self, backend, model=None):
        self.backend, self.model = backend, model
        self._last_ts = -1
        self._h = self._ctx = None

    def __enter__(self):
        if self.backend == "vision":
            Holistic = _vision_attr("signer_core.vision.holistic", "Holistic")
            self._ctx = Holistic()
            self._h = self._ctx.__enter__()
        elif self.backend == "tasks":
            import mediapipe as mp  # noqa: F401
            from mediapipe.tasks.python import BaseOptions
            from mediapipe.tasks.python import vision as mp_vision

            opts = mp_vision.HolisticLandmarkerOptions(
                base_options=BaseOptions(model_asset_path=str(self.model)),
                running_mode=mp_vision.RunningMode.VIDEO,
                min_pose_detection_confidence=0.5,
                min_hand_landmarks_confidence=0.5,
                output_face_blendshapes=False,
            )
            self._h = mp_vision.HolisticLandmarker.create_from_options(opts)
        elif self.backend == "legacy":
            import mediapipe as mp

            self._h = mp.solutions.holistic.Holistic(
                model_complexity=1, static_image_mode=False, refine_face_landmarks=False
            )
        else:
            raise ValueError(self.backend)
        self._to75 = resolve_results_to_75()
        return self

    def __exit__(self, *exc):
        if self._ctx is not None:
            self._ctx.__exit__(*exc)
        elif self._h is not None:
            self._h.close()
        self._h = self._ctx = None
        return False

    def process_bgr(self, frame_bgr, ts_ms):
        ts = max(int(ts_ms), self._last_ts + 1)
        self._last_ts = ts
        if self.backend == "vision":
            return self._h.process(frame_bgr, ts, bgr=True)[0]
        import cv2

        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        if self.backend == "tasks":
            import mediapipe as mp

            res = self._h.detect_for_video(mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb), ts)
        else:
            rgb.flags.writeable = False
            res = self._h.process(rgb)
        return self._to75(res)


# --------------------------------------------------------------------------------------------
# VOCAB.md and filename handling
# --------------------------------------------------------------------------------------------
_ROW = re.compile(r"^\|\s*([A-Z][A-Z0-9_-]*)\s*\|(.*)\|\s*$")


def parse_vocab(path):
    """Parse `| GLOSS | english | source | popsign_name |` rows (source must be popsign or own)."""
    rows = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        m = _ROW.match(line)
        if not m:
            continue
        cells = [c.strip().strip("`") for c in m.group(2).split("|")]
        cells += [""] * (3 - len(cells))
        english, source, pop = cells[0], cells[1].lower(), cells[2]
        if source not in ("popsign", "own"):
            continue  # header or separator
        if pop in ("-", "—", "n/a", "N/A"):
            pop = ""
        rows.append(VocabRow(m.group(1), english, source, pop))
    return rows


def _norm(s):
    return re.sub(r"[^a-z0-9]", "", s.lower())


def popsign_keymap(rows):
    """normalised popsign name -> GLOSS, for popsign-sourced rows (falls back to the gloss itself)."""
    km = {}
    for r in rows:
        if r.source != "popsign":
            continue
        km[_norm(r.popsign_name or r.gloss)] = r.gloss
    return km


_UUID = re.compile(r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}")
_SIGNER_TAG = re.compile(r"(?:signer|participant|user)[-_]?([A-Za-z0-9]+)", re.I)


def infer_gloss_and_signer(path, keymap):
    """Return (GLOSS, signer, clip_id) or (None, ..) if the sign can't be mapped.

    Sign: the parent folder name if it is a vocabulary popsign_name, else the first filename token
    run (up to 4 tokens, split on - _ . space) that is one. Signer (the PopSign naming was not
    verified; heuristics): a uuid in the stem, else signer-/participant-<id>, else the tokens
    before the sign in the filename, else the first non-numeric token after it, else 'unknown'."""
    path = Path(path)
    stem = path.stem
    clip_id = re.sub(r"[^A-Za-z0-9._-]", "_", stem)
    tokens = [t for t in re.split(r"[-_.\s]+", stem) if t]
    gloss, span = None, None
    for n in (4, 3, 2, 1):  # sign tokens inside the filename (also locates the signer prefix)
        for i in range(len(tokens) - n + 1):
            g = keymap.get(_norm("".join(tokens[i : i + n])))
            if g:
                gloss, span = g, (i, i + n)
                break
        if gloss:
            break
    gloss = keymap.get(_norm(path.parent.name)) or gloss  # the parent folder wins
    if gloss is None:
        return None, "unknown", clip_id
    signer = None
    m = _UUID.search(stem) or _SIGNER_TAG.search(stem)
    if m:
        signer = m.group(1) if m.re is _SIGNER_TAG else m.group(0)
    elif span:
        before = tokens[: span[0]]
        after = [t for t in tokens[span[1] :] if not re.fullmatch(r"\d{1,4}", t)]
        signer = "-".join(before) or (after[0] if after else None)
    signer = re.sub(r"[^A-Za-z0-9-]", "", signer or "") or "unknown"
    return gloss, signer, clip_id


# --------------------------------------------------------------------------------------------
# Extraction
# --------------------------------------------------------------------------------------------
def extract_video(video, runner_factory, max_side=960):
    """Run Holistic over a video. Returns (xyz float32 (T,75,3), t_ms int64 (T,), fps)."""
    import cv2
    import numpy as np

    cap = cv2.VideoCapture(str(video))
    try:
        cap.set(cv2.CAP_PROP_ORIENTATION_AUTO, 1)  # honour rotation metadata (phone selfie videos)
    except Exception:
        pass
    if not cap.isOpened():
        raise IOError("cannot open video")
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 0)
    if not 1.0 <= fps <= 240.0:
        fps = 30.0
    frames, t_list = [], []
    try:
        with runner_factory() as runner:
            i = 0
            while True:
                ok, frame = cap.read()
                if not ok:
                    break
                h, w = frame.shape[:2]
                if max_side and max(h, w) > max_side:
                    s = max_side / max(h, w)
                    frame = cv2.resize(frame, (max(1, round(w * s)), max(1, round(h * s))), interpolation=cv2.INTER_AREA)
                t = round(i * 1000 / fps)
                frames.append(runner.process_bgr(frame, t))
                t_list.append(t)
                i += 1
    finally:
        cap.release()
    if not frames:
        raise IOError("no frames decoded")
    return np.stack(frames).astype(np.float32), np.asarray(t_list, dtype=np.int64), fps


_STATE = {}


def _init_worker(backend, model, max_side):
    _STATE.update(backend=backend, model=model, max_side=max_side)


def _process_job(job):
    """Worker: extract one video -> npz -> verify -> delete video. Returns a result dict."""
    import numpy as np

    video, out_path, gloss, signer, keep = job
    res = {"video": video, "gloss": gloss, "clip": Path(out_path).stem, "status": "ok", "frames": 0, "hand_frames": 0, "msg": ""}
    try:
        xyz, t_ms, fps = extract_video(
            video, lambda: HolisticRunner(_STATE["backend"], _STATE["model"]), _STATE["max_side"]
        )
        res["frames"] = int(xyz.shape[0])
        if not (~np.isnan(xyz[:, :POSE_N, 0])).any():
            res.update(status="no_pose", msg="no pose detected in any frame")
            return res
        res["hand_frames"] = int((~np.isnan(xyz[:, POSE_N:, 0])).any(axis=1).sum())
        write_clip(out_path, xyz, t_ms, fps, gloss, signer, "popsign")
        verify_clip(out_path, n_frames=xyz.shape[0], gloss=gloss, source="popsign")
        if not keep:
            os.remove(video)
            try:
                Path(video).parent.rmdir()  # only succeeds if empty
            except OSError:
                pass
    except Exception as e:  # one bad clip must not stop the batch
        res.update(status="failed", msg=f"{type(e).__name__}: {e}")
        p = Path(out_path)
        if p.exists():  # an unverified npz must not count as done on resume
            try:
                p.unlink()
            except OSError:
                pass
    return res


def find_videos(root):
    return sorted(p for p in Path(root).rglob("*") if p.is_file() and p.suffix.lower() in VIDEO_EXTS)


def parse_shard(s):
    m = re.fullmatch(r"(\d+)/(\d+)", s or "")
    if not m or not (0 <= int(m.group(1)) < int(m.group(2))):
        raise argparse.ArgumentTypeError("--shard must be i/n with 0 <= i < n, e.g. 0/2 and 1/2")
    return int(m.group(1)), int(m.group(2))


def run_extract(args):
    rows = parse_vocab(args.vocab) if Path(args.vocab).exists() else None
    if rows is None:
        print(f"error: vocab file not found: {args.vocab}", file=sys.stderr)
        return 2
    keymap = popsign_keymap(rows)
    if not keymap:
        print(f"error: no popsign rows in {args.vocab}", file=sys.stderr)
        return 2
    in_dir, out_dir = Path(args.in_dir), Path(args.out)
    if not in_dir.exists():
        print(f"error: input folder not found: {in_dir}", file=sys.stderr)
        return 2
    videos = find_videos(in_dir)
    if args.shard:
        i, n = args.shard
        videos = videos[i::n]
    jobs, unmapped, skipped = [], [], 0
    for v in videos:
        gloss, signer, clip_id = infer_gloss_and_signer(v, keymap)
        if gloss is None:
            unmapped.append(v)
            continue
        out_path = out_dir / gloss / f"{clip_id}.npz"
        if out_path.exists():
            skipped += 1
            continue
        jobs.append((str(v), str(out_path), gloss, signer, args.keep_videos))
    if args.limit is not None:
        jobs = jobs[: args.limit]
    for v in unmapped[:20]:
        print(f"unmapped (not in vocab): {v}")
    if len(unmapped) > 20:
        print(f"... and {len(unmapped) - 20} more unmapped")
    total = len(jobs)
    print(f"extract plan: {total} to do, {skipped} already done, {len(unmapped)} unmapped, of {len(videos)} videos in {in_dir}", flush=True)
    if not total:
        return 0

    backend, model = choose_backend(args.backend)
    print(f"backend: {backend}", flush=True)
    workers = max(1, min(args.workers, total))
    t0 = time.time()
    results, done = [], 0

    def report(r):
        nonlocal done
        done += 1
        results.append(r)
        tail = f" T={r['frames']}" if r["status"] == "ok" else f" [{r['status']}] {r['msg']}"
        print(f"extract {done}/{total} {r['gloss']}/{r['clip']}{tail}", flush=True)

    if workers == 1:
        _init_worker(backend, model, args.max_side)
        for j in jobs:
            report(_process_job(j))
    else:
        import multiprocessing as mp

        ctx = mp.get_context("spawn")
        with ctx.Pool(workers, initializer=_init_worker, initargs=(backend, model, args.max_side)) as pool:
            for r in pool.imap_unordered(_process_job, jobs):
                report(r)

    ok = [r for r in results if r["status"] == "ok"]
    bad = [r for r in results if r["status"] != "ok"]
    frames = sum(r["frames"] for r in ok)
    hands = sum(r["hand_frames"] for r in ok)
    if bad:
        out_dir.mkdir(parents=True, exist_ok=True)
        with open(out_dir / "_extract_failures.log", "a", encoding="utf-8") as f:
            for r in bad:
                f.write(f"{time.strftime('%F %T')}\t{r['status']}\t{r['video']}\t{r['msg']}\n")
    share = hands / frames if frames else 0.0
    print(
        f"summary: ok={len(ok)} failed={len(bad)} (no_pose={sum(r['status'] == 'no_pose' for r in bad)}) "
        f"frames={frames} hand_frames={share:.1%} elapsed={time.time() - t0:.0f}s videos_kept={'all' if args.keep_videos else 'only failed'}",
        flush=True,
    )
    return 0 if ok or not bad else 1


# --------------------------------------------------------------------------------------------
# Self-test (numpy only)
# --------------------------------------------------------------------------------------------
def selftest():
    import tempfile
    from types import SimpleNamespace as NS

    import numpy as np

    rng = np.random.default_rng(0)

    def lm(n):
        return [NS(x=float(a), y=float(b), z=float(c)) for a, b, c in rng.random((n, 3))]

    def expect(_unused, container):
        pts = _flat(container)
        return np.array([[p.x, p.y, p.z] for p in pts], dtype=np.float32)

    pose, lh, rh = lm(33), lm(21), lm(21)
    tasks = NS(pose_landmarks=pose, left_hand_landmarks=lh, right_hand_landmarks=rh, face_landmarks=[])
    tasks_nested = NS(pose_landmarks=[pose], left_hand_landmarks=[lh], right_hand_landmarks=[rh])
    legacy = NS(pose_landmarks=NS(landmark=pose), left_hand_landmarks=NS(landmark=lh), right_hand_landmarks=NS(landmark=rh))
    only_right = NS(pose_landmarks=None, left_hand_landmarks=[], right_hand_landmarks=rh)
    nothing = NS(pose_landmarks=None, left_hand_landmarks=None, right_hand_landmarks=None)

    ref = np.concatenate([expect(None, pose), expect(None, lh), expect(None, rh)])
    for label, r in (("tasks", tasks), ("tasks-nested", tasks_nested), ("legacy", legacy)):
        a = results_to_75(r)
        assert a.shape == (75, 3) and a.dtype == np.float32, (label, a.shape, a.dtype)
        assert np.array_equal(a, ref), label
        assert not np.isnan(a).any(), label
    a = results_to_75(only_right)
    assert np.isnan(a[:54]).all() and np.array_equal(a[54:], expect(None, rh)), "only right hand"
    assert np.array_equal(results_to_75(NS(pose_landmarks=pose))[:33], ref[:33])  # missing attrs -> NaN
    assert np.isnan(results_to_75(NS(pose_landmarks=pose))[33:]).all()
    assert np.isnan(results_to_75(nothing)).all(), "all missing"
    # left stays left: the left-hand rows are the left_hand_landmarks, never swapped
    swapped = NS(pose_landmarks=None, left_hand_landmarks=lh, right_hand_landmarks=None)
    a = results_to_75(swapped)
    assert np.array_equal(a[33:54], expect(None, lh)) and np.isnan(a[54:]).all()
    print("ok  results_to_75: tasks, nested tasks, legacy, partial, empty")

    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "G" / "clip1.npz"
        xyz = np.stack([ref, results_to_75(only_right), results_to_75(nothing)])
        write_clip(p, xyz, [0, 33, 67], 30.0, "HELLO", "s7", "popsign")
        assert not list(p.parent.glob("*.tmp.npz")), "temp file left behind"
        with np.load(p, allow_pickle=False) as z:
            assert set(z.files) == set(CLIP_KEYS), z.files
            assert z["xyz"].dtype == np.float16 and z["xyz"].shape == (3, 75, 3)
            assert z["t_ms"].dtype == np.int64 and z["fps"].dtype == np.float32
            assert (str(z["gloss"]), str(z["signer"]), str(z["source"])) == ("HELLO", "s7", "popsign")
            assert np.isnan(z["xyz"][2]).all() and np.isnan(z["xyz"][1, :54]).all()
        assert verify_clip(p, n_frames=3, gloss="HELLO", source="popsign") == 3
        try:
            verify_clip(p, n_frames=4)
            raise AssertionError("verify_clip accepted wrong T")
        except ValueError:
            pass
        try:
            write_clip(Path(d) / "bad.npz", np.zeros((2, 74, 3)), [0, 1], 30, "X", "s1", "own")
            raise AssertionError("write_clip accepted wrong shape")
        except ValueError:
            pass
        print("ok  write_clip / verify_clip: keys == contracts.CLIP_KEYS, dtypes, NaN preserved")

    rows = [VocabRow("HELLO", "hello", "popsign", "hello"), VocabRow("THANK_YOU", "thank you", "popsign", "thankyou"),
            VocabRow("MINE", "mine", "own", "")]
    km = popsign_keymap(rows)
    cases = [
        ("raw/hello/abc123-hello-4.mp4", ("HELLO", "abc123")),
        ("raw/thankyou/0.mp4", ("THANK_YOU", "unknown")),
        ("raw/x/s12_thank_you_003.mp4", ("THANK_YOU", "s12")),
        ("raw/hello/signer7_take2.mp4", ("HELLO", "7")),
        ("raw/hello/3f2b9c1e-1111-2222-3333-444455556666-hello.mp4", ("HELLO", "3f2b9c1e-1111-2222-3333-444455556666")),
        ("raw/mine/a.mp4", (None, "unknown")),
    ]
    for rel, (g, s) in cases:
        got = infer_gloss_and_signer(rel, km)
        assert (got[0], got[1]) == (g, s), (rel, got)
    print("ok  gloss/signer inference from folder and filename")

    vision_fn = None
    for modname in ("signer_core.vision.landmarks", "signer_core.vision"):
        vision_fn = _vision_attr(modname, "results_to_75")
        if vision_fn:
            break
    if vision_fn is None:
        print("skip signer_core.vision.results_to_75 not importable; local implementation is the only one")
    else:
        for label, r in (("tasks", tasks), ("nested", tasks_nested), ("legacy", legacy), ("partial", only_right), ("empty", nothing)):
            assert np.array_equal(np.asarray(vision_fn(r), dtype=np.float32), results_to_75(r), equal_nan=True), label
        print("ok  signer_core.vision.results_to_75 == local results_to_75")
    print("selftest passed")
    return 0


def build_parser():
    ap = argparse.ArgumentParser(
        description="Extract 75-point Holistic landmarks from PopSign videos into .npz clips and delete the videos.",
    )
    ap.add_argument("--in", dest="in_dir", default=str(DEFAULT_IN), help="video root (default data/popsign/raw)")
    ap.add_argument("--vocab", default=str(DEFAULT_VOCAB), help="VOCAB.md mapping popsign_name -> GLOSS")
    ap.add_argument("--out", default=str(DEFAULT_OUT), help="output root (default data/popsign/landmarks)")
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1), help="processes (default cpu-1; 1 = in-process)")
    ap.add_argument("--shard", type=parse_shard, default=None, metavar="I/N", help="process shard I of N (0-based), to split across laptops")
    ap.add_argument("--keep-videos", action="store_true", help="keep source videos (default: delete after verified npz)")
    ap.add_argument("--limit", type=int, default=None, help="process at most N clips (after skipping finished ones)")
    ap.add_argument("--max-side", type=int, default=960, help="downscale frames so the long side is at most this (0 = off)")
    ap.add_argument("--backend", choices=("auto", "local"), default="auto", help="auto prefers signer_core.vision; local forces this file's Tasks/legacy path")
    ap.add_argument("--selftest", action="store_true", help="run numpy-only self-tests and exit")
    return ap


def main(argv=None):
    args = build_parser().parse_args(argv)
    if args.selftest:
        return selftest()
    return run_extract(args)


if __name__ == "__main__":
    sys.exit(main())
