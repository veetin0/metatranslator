#!/usr/bin/env python
"""Consented webcam landmark recorder for our own clips (source='own').

Saves ONLY landmark coordinates (CONTRACTS section 5): data/landmarks/<signer>/<GLOSS>/<n>.npz.
Never saves frames or video (R3). The OpenCV window shows a live preview (mirrored for comfort, display only;
landmarks are computed on the un-mirrored frame) plus the prompt; nothing from the preview is written anywhere.

  python core/tools/record.py --dry-run                      # plan only: no camera, nothing written, exit 0
  python core/tools/record.py --signer s1                    # asks for a typed 'yes', then records
  python core/tools/record.py --signer s1 --signs HELLO,YES  # subset
Keys in the window: SPACE = record the prompted clip, r = redo (delete) the last clip saved in this session, q = quit.

Landmark conversion, clip writing and VOCAB.md parsing are imported from extract_landmarks.py (one implementation).
Only the stdlib is imported at module level; cv2 / numpy / mediapipe are imported lazily.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # repo root
CORE = Path(__file__).resolve().parents[1]  # core/
TOOLS = Path(__file__).resolve().parent
for _p in (str(CORE), str(TOOLS)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from extract_landmarks import (  # noqa: E402
    DEFAULT_VOCAB,
    HolisticRunner,
    VocabRow,
    choose_backend,
    parse_vocab,
    write_clip,
)
from signer_core.contracts import REST  # noqa: E402

SIGNER_RE = re.compile(r"^s\d+$")
MIN_ROWS = 25

# Used by --dry-run only when data/VOCAB.md does not exist yet. The real vocabulary is data/VOCAB.md.
SAMPLE_VOCAB = [
    VocabRow(g, e, "popsign", e.lower())
    for g, e in [
        ("HELLO", "hello"), ("THANK_YOU", "thank you"), ("PLEASE", "please"), ("YES", "yes"), ("NO", "no"),
        ("HELP", "help"), ("SORRY", "sorry"), ("WATER", "water"), ("EAT", "eat"), ("DRINK", "drink"),
        ("GOOD", "good"), ("BAD", "bad"), ("WANT", "want"), ("NEED", "need"), ("LIKE", "like"),
        ("LOVE", "love"), ("FRIEND", "friend"), ("FAMILY", "family"), ("HOME", "home"), ("WORK", "work"),
        ("TODAY", "today"), ("TOMORROW", "tomorrow"), ("WHERE", "where"), ("WHAT", "what"),
    ]
] + [VocabRow(REST, "rest (hands down)", "own", "")]


def validate_vocab(rows):
    """Return a list of problems (empty = ok): >= 25 rows, REST present, glosses unique."""
    problems = []
    if len(rows) < MIN_ROWS:
        problems.append(f"only {len(rows)} vocabulary rows, need >= {MIN_ROWS} (24 signs + {REST})")
    glosses = [r.gloss for r in rows]
    if REST not in glosses:
        problems.append(f"{REST} row missing")
    dupes = sorted({g for g in glosses if glosses.count(g) > 1})
    if dupes:
        problems.append(f"duplicate glosses: {', '.join(dupes)}")
    return problems


def data_dir():
    d = Path(os.environ.get("SIGNER_DATA_DIR", "data"))
    return d if d.is_absolute() else ROOT / d


def _rel(p):
    p = Path(p)
    return p.relative_to(ROOT) if p.is_relative_to(ROOT) else p


def clip_dir(signer, gloss, base=None):
    return (base or data_dir()) / "landmarks" / signer / gloss


def next_free(signer, gloss, base=None):
    """Next unused clip number n (1-based): one above the highest existing <n>.npz."""
    d = clip_dir(signer, gloss, base)
    nums = [int(p.stem) for p in d.glob("*.npz") if p.stem.isdigit()] if d.exists() else []
    return max(nums, default=0) + 1


def make_plan(rows, signer, reps, signs=None, base=None):
    """[(gloss, first_n, count)] for the glosses still short of `reps` clips (tops up existing folders)."""
    plan = []
    for r in rows:
        if signs and r.gloss not in signs:
            continue
        d = clip_dir(signer, r.gloss, base)
        have = len(list(d.glob("*.npz"))) if d.exists() else 0
        need = reps - have
        if need > 0:
            plan.append((r.gloss, next_free(signer, r.gloss, base), need))
    return plan


def load_rows(vocab_path, allow_sample):
    """(rows, note). Missing VOCAB.md falls back to SAMPLE_VOCAB only when allow_sample (dry-run)."""
    p = Path(vocab_path)
    if p.exists():
        return parse_vocab(p), f"vocab: {p}"
    if allow_sample:
        print(f"WARNING: vocab file not found: {p}; validating the built-in {len(SAMPLE_VOCAB)}-row sample vocabulary instead "
              "(data/VOCAB.md is written by another task)", file=sys.stderr)
        return list(SAMPLE_VOCAB), "vocab: built-in sample (VOCAB.md missing)"
    raise SystemExit(f"error: vocab file not found: {p}")


def split_signs(values):
    out = []
    for v in values or []:
        out += [s.strip().upper() for s in v.split(",") if s.strip()]
    return out or None


def dry_run(args):
    signer = args.signer or "s0"
    rows, note = load_rows(args.vocab, allow_sample=True)
    problems = validate_vocab(rows)
    print(f"dry run (no camera, nothing written): signer={signer} reps={args.reps} seconds={args.seconds} {note}")
    print(f"vocabulary: {len(rows)} rows, {REST} {'present' if any(r.gloss == REST for r in rows) else 'MISSING'}, "
          f"glosses {'unique' if not any('duplicate' in p for p in problems) else 'NOT unique'}")
    if problems:
        for p in problems:
            print(f"error: {p}", file=sys.stderr)
        return 1
    signs = split_signs(args.signs)
    if signs:
        unknown = [s for s in signs if s not in {r.gloss for r in rows}]
        if unknown:
            print(f"error: unknown signs: {', '.join(unknown)}", file=sys.stderr)
            return 2
    base = data_dir()
    for r in rows:
        if signs and r.gloss not in signs:
            continue
        d = clip_dir(signer, r.gloss, base)
        have = len(list(d.glob("*.npz"))) if d.exists() else 0
        need, n = max(0, args.reps - have), next_free(signer, r.gloss, base)
        if not need:
            print(f"  {r.gloss:<12} already has {have} clips (>= {args.reps})")
            continue
        last = f" .. {_rel(d / f'{n + need - 1}.npz')}" if need > 1 else ""
        print(f"  {r.gloss:<12} next n={n:<3} -> {_rel(d / f'{n}.npz')}{last}  ({need} to record)")
    print("ok")
    return 0


# --------------------------------------------------------------------------------------------
# Real recording
# --------------------------------------------------------------------------------------------
CONSENT_TEXT = """
Signer landmark recording: consent
  - The webcam is used live. Only LANDMARK COORDINATES (body pose + hand points) are saved.
  - No video, no frames, no images and no face data are stored. The preview window is never recorded.
  - Clips are saved as pseudonym '{signer}' in data/landmarks/{signer}/<SIGN>/<n>.npz and may be used to train and
    evaluate the Signer sign recognizer. You can delete them any time (press r to redo the last one, or delete the folder).
Type 'yes' to consent and start the camera, anything else to cancel: """


def capture_clip(cap, runner_factory, seconds, show, flip=True):
    """Record `seconds` of landmarks. Returns (xyz (T,75,3) float32, t_ms int64, fps) or None if the camera failed."""
    import numpy as np

    frames, ts = [], []
    with runner_factory() as runner:
        t0 = time.monotonic()  # after model load, so t_ms starts near 0
        while (time.monotonic() - t0) < seconds:
            ok, frame = cap.read()
            if not ok:
                break
            t_ms = int((time.monotonic() - t0) * 1000)
            frames.append(runner.process_bgr(frame, t_ms))
            ts.append(t_ms)
            if show(frame, f"REC {max(0.0, seconds - t_ms / 1000):.1f}s", (0, 0, 255)) == ord("q"):
                return None
    if len(frames) < 2:
        return None
    t_arr = np.asarray(ts, dtype=np.int64)
    fps = (len(frames) - 1) * 1000.0 / max(1, int(t_arr[-1] - t_arr[0]))
    return np.stack(frames).astype(np.float32), t_arr, float(fps)


def record_session(args, rows):
    import cv2
    import numpy as np

    signs = split_signs(args.signs)
    plan = make_plan(rows, args.signer, args.reps, signs)
    if not plan:
        print(f"nothing to record: every selected sign already has {args.reps} clips for {args.signer}")
        return 0
    descr = {r.gloss: r.english for r in rows}
    backend, model = choose_backend("auto")
    cap = cv2.VideoCapture(args.camera)
    if not cap.isOpened():
        print(f"error: cannot open camera {args.camera} (try --camera 1; macOS: allow the terminal in Camera settings)", file=sys.stderr)
        return 1
    win = "Signer record (SPACE record, r redo, q quit)"
    saved = []  # paths written this session, newest last
    state = {"msg": ""}

    def show(frame, banner, color, sub=""):
        img = cv2.flip(frame, 1)  # display only
        h, w = img.shape[:2]
        cv2.rectangle(img, (0, 0), (w, 70), (0, 0, 0), -1)
        cv2.putText(img, banner, (12, 46), cv2.FONT_HERSHEY_SIMPLEX, 1.2, color, 3, cv2.LINE_AA)
        if sub or state["msg"]:
            cv2.putText(img, sub or state["msg"], (12, h - 16), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2, cv2.LINE_AA)
        cv2.imshow(win, img)
        return cv2.waitKey(1) & 0xFF

    def new_runner():
        return HolisticRunner(backend, model)

    tasks = [(g, n0 + k) for g, n0, count in plan for k in range(count)]
    i = 0  # index of the clip being recorded; redo steps it back one slot
    try:
        while i < len(tasks):
            gloss, n = tasks[i]
            label = f"{gloss}  ({descr.get(gloss, '')})  {i + 1}/{len(tasks)}"
            key = -1
            while key not in (ord(" "), ord("r"), ord("q")):
                ok, frame = cap.read()
                if not ok:
                    print("error: camera stopped delivering frames", file=sys.stderr)
                    return 1
                key = show(frame, label, (0, 255, 0), "SPACE record | r redo last | q quit")
            if key == ord("q"):
                break
            if key == ord("r"):
                if saved:
                    last = saved.pop()
                    last.unlink(missing_ok=True)
                    i -= 1
                    state["msg"] = f"deleted {last.parent.name}/{last.name}; record it again"
                    print(state["msg"], flush=True)
                else:
                    state["msg"] = "nothing to redo"
                continue
            t_end = time.monotonic() + 3.0  # countdown 3, 2, 1
            aborted = False
            while time.monotonic() < t_end:
                ok, frame = cap.read()
                if not ok:
                    break
                if show(frame, f"{gloss}  in {int(t_end - time.monotonic()) + 1}", (0, 200, 255)) == ord("q"):
                    aborted = True
                    break
            if aborted:
                break
            clip = capture_clip(cap, new_runner, args.seconds, show)
            if clip is None:
                state["msg"] = "capture failed or interrupted; try again"
                continue
            xyz, t_ms, fps = clip
            pose_share = float((~np.isnan(xyz[:, :33, 0])).mean())
            if pose_share < 0.5:
                state["msg"] = f"body seen in only {pose_share:.0%} of frames; step back / light the room, then retry"
                continue
            path = clip_dir(args.signer, gloss) / f"{n}.npz"
            write_clip(path, xyz, t_ms, fps, gloss, args.signer, "own")
            saved.append(path)
            hands = float((~np.isnan(xyz[:, 33:, 0])).any(axis=1).mean())
            state["msg"] = f"saved {_rel(path)}  T={len(xyz)} fps={fps:.0f} hands={hands:.0%}"
            print(state["msg"], flush=True)
            i += 1
        print(f"stopped at {i}/{len(tasks)} clips for {args.signer}" if i < len(tasks) else f"done: {len(tasks)} clips for {args.signer}")
        return 0
    except cv2.error as e:
        print(f"error: OpenCV window failed ({e}); install opencv-python (not -headless)", file=sys.stderr)
        return 1
    finally:
        cap.release()
        cv2.destroyAllWindows()


def build_parser():
    ap = argparse.ArgumentParser(description="Record own landmark clips from the webcam (landmarks only, never video).")
    ap.add_argument("--signer", default=None, help="pseudonym matching ^s\\d+$, e.g. s1 (required unless --dry-run)")
    ap.add_argument("--vocab", default=str(DEFAULT_VOCAB), help="VOCAB.md (default data/VOCAB.md)")
    ap.add_argument("--reps", type=int, default=20, help="clips per sign (default 20; tops up existing folders)")
    ap.add_argument("--signs", nargs="+", default=None, metavar="GLOSS", help="subset of glosses, comma or space separated")
    ap.add_argument("--camera", type=int, default=0, help="OpenCV camera index (default 0)")
    ap.add_argument("--seconds", type=float, default=2.0, help="seconds of landmarks per clip (default 2.0)")
    ap.add_argument("--dry-run", action="store_true", help="validate the vocab and print the planned paths; no camera, no writes")
    return ap


def main(argv=None):
    args = build_parser().parse_args(argv)
    if args.reps < 1 or args.seconds <= 0:
        print("error: --reps must be >= 1 and --seconds > 0", file=sys.stderr)
        return 2
    if args.signer is not None and not SIGNER_RE.match(args.signer):
        print(f"error: --signer must match ^s\\d+$ (a pseudonym such as s1), got {args.signer!r}", file=sys.stderr)
        return 2
    if args.dry_run:
        return dry_run(args)
    if not args.signer:
        print("error: --signer is required (e.g. --signer s1)", file=sys.stderr)
        return 2
    rows, _ = load_rows(args.vocab, allow_sample=False)
    problems = validate_vocab(rows)
    if problems:
        print("error: " + "; ".join(problems), file=sys.stderr)
        return 1
    signs = split_signs(args.signs)
    if signs:
        unknown = [s for s in signs if s not in {r.gloss for r in rows}]
        if unknown:
            print(f"error: unknown signs: {', '.join(unknown)}", file=sys.stderr)
            return 2
    try:
        answer = input(CONSENT_TEXT.format(signer=args.signer))
    except EOFError:
        answer = ""
    if answer.strip().lower() != "yes":
        print("no consent given; camera not opened, nothing recorded")
        return 1
    return record_session(args, rows)


if __name__ == "__main__":
    sys.exit(main())
