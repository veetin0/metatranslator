#!/usr/bin/env python3
"""Signer eval harness: leave-one-signer-out (LOSO) over landmark clips (CONTRACTS.md section 6).

    python eval/run.py --loso [--source own|popsign|glasses] [--data-dir data]
                       [--out eval/results/<name>.json] [--report] [--model auto|baseline]

Protocol (see eval/README.md): every signer is held out once. Own and glasses signers are one fold each;
PopSign signers are grouped into --popsign-folds (default 5) deterministic signer-disjoint folds. For each fold the
model is fitted on every clip of every selected source whose signer is NOT in the fold and then predicts each
held-out clip. Each clip is tested exactly once, so n_clips = number of clips evaluated.

Needs numpy (and matplotlib only for --report). The classifier is behind the tiny `Adapter` interface below: the
built-in baseline (centred-cosine kNN on flat_features) is used unless `signer_core.model` offers a classifier.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parent.parent
if str(REPO / "core") not in sys.path:
    sys.path.insert(0, str(REPO / "core"))

from signer_core import contracts  # noqa: E402
from signer_core.vision.clip import load_clip  # noqa: E402
from signer_core.vision.features import flat_features  # noqa: E402

SOURCES = ("own", "popsign", "glasses")
TOPK = 3
LATENCY_PER_FOLD = 30  # clips timed one by one per fold (features + predict), seeded subsample


class EvalError(Exception):
    """User-facing failure (no data, too few signers, ...): printed, exit code 2."""


# ----------------------------------------------------------------------------------------------- data
class Clip:
    """One landmark clip. `feat` (flat_features) is computed on first use and cached."""

    __slots__ = ("xyz", "gloss", "signer", "source", "path", "_feat")

    def __init__(self, xyz, gloss, signer, source, path=""):
        self.xyz, self.gloss, self.signer, self.source, self.path = xyz, gloss, signer, source, path
        self._feat = None

    @property
    def feat(self) -> np.ndarray:
        if self._feat is None:
            self._feat = flat_features(self.xyz).astype(np.float32)
        return self._feat

    @property
    def unit(self):  # signer identity is only unique within a source
        return (self.source, self.signer)


def source_glob(data_dir: Path, source: str) -> list[Path]:
    if source == "own":
        return sorted(data_dir.glob("landmarks/*/*/*.npz"))
    if source == "popsign":
        return sorted(data_dir.glob("popsign/landmarks/*/*.npz"))
    if source == "glasses":
        return sorted(data_dir.glob("glasses/*/*/*.npz"))
    raise EvalError(f"unknown source {source!r}")


def load_clips(data_dir: Path, sources) -> tuple[list[Clip], dict]:
    clips, skipped = [], []
    for src in sources:
        for p in source_glob(data_dir, src):
            try:
                c = load_clip(p)
            except Exception as e:  # invalid file: counted and reported, never silently trusted
                skipped.append((str(p), f"{type(e).__name__}: {e}"))
                continue
            if c["source"] != src and not (src == "own" and c["source"] == "webcam"):
                skipped.append((str(p), f"source {c['source']!r} in a {src} directory"))
                continue
            clips.append(Clip(c["xyz"], c["gloss"], c["signer"], src, str(p)))
    for path, why in skipped[:5]:
        print(f"warning: skipped {path}: {why}", file=sys.stderr)
    if len(skipped) > 5:
        print(f"warning: ... and {len(skipped) - 5} more skipped clips", file=sys.stderr)
    return clips, {"n_skipped": len(skipped)}


def make_folds(clips: list[Clip], popsign_folds: int, seed: int) -> list[dict]:
    """Signer-disjoint folds: [{"name", "units": {(source, signer), ...}}] in a deterministic order."""
    by_source: dict[str, set] = {}
    for c in clips:
        by_source.setdefault(c.source, set()).add(c.signer)
    folds = []
    for src in ("own", "glasses"):
        for s in sorted(by_source.get(src, ())):
            folds.append({"name": f"{src}:{s}", "units": {(src, s)}})
    pops = sorted(by_source.get("popsign", ()))
    if pops:
        k = max(1, min(popsign_folds, len(pops)))
        order = sorted(pops, key=lambda s: hashlib.sha1(f"{seed}:{s}".encode()).hexdigest())
        groups = [set() for _ in range(k)]
        for i, s in enumerate(order):
            groups[i % k].add(("popsign", s))
        folds += [{"name": f"popsign:fold{i}", "units": g} for i, g in enumerate(groups)]
    return folds


# ------------------------------------------------------------------------------------------ classifiers
class Adapter:
    """What the harness needs from a classifier. Point this at the real model by subclassing / wrapping.

    fit(train: list[Clip]) ; predict(clip) -> ranked [(gloss, confidence), ...] best first, at least top-3 when
    that many classes exist; confidence in [0, 1] (the harness maps it to tiers with SIGNER_CONF_HIGH / LOW).
    predict_many(clips) may be overridden for speed; it must give the same answers as looping predict.
    """

    name = "adapter"

    def fit(self, train: list[Clip]) -> None:
        raise NotImplementedError

    def predict(self, clip: Clip):
        raise NotImplementedError

    def predict_many(self, clips: list[Clip]):
        return [self.predict(c) for c in clips]


class BaselineKnn(Adapter):
    """Cosine kNN (k=5, distance-weighted vote) on flat_features, centred on the train mean.

    Vote weight of a neighbour = 1 / (1 - cos + 1e-3); confidence of a class = its share of the total weight.
    Classes the neighbours miss are ranked after the voted ones by their best single-clip similarity so top-3
    is well defined (their confidence is 0).
    """

    name = "baseline-knn"

    def __init__(self, k: int = 5):
        self.k = k

    def fit(self, train):
        if not train:
            raise EvalError("empty training set")
        x = np.stack([c.feat for c in train]).astype(np.float32)
        labels = np.array([c.gloss for c in train])
        order = np.argsort(labels, kind="stable")
        x, labels = x[order], labels[order]
        self.mean = x.mean(axis=0)
        self.x = self._unit(x - self.mean)
        self.classes, self.starts, self.y = np.unique(labels, return_index=True, return_inverse=True)

    @staticmethod
    def _unit(a):
        n = np.linalg.norm(a, axis=1, keepdims=True)
        return a / np.maximum(n, 1e-9)

    def _rank(self, sims_row, k):
        n_cls = len(self.classes)
        idx = np.argpartition(-sims_row, k - 1)[:k]
        w = 1.0 / (np.maximum(1.0 - sims_row[idx], 0.0) + 1e-3)
        votes = np.bincount(self.y[idx], weights=w, minlength=n_cls)
        prob = votes / max(votes.sum(), 1e-12)
        best = np.maximum.reduceat(sims_row, self.starts)  # best similarity per class (classes are contiguous)
        order = np.lexsort((-best, -prob))
        return [(str(self.classes[i]), float(prob[i])) for i in order[: max(TOPK, 1)]]

    def predict_many(self, clips):
        if not clips:
            return []
        q = self._unit(np.stack([c.feat for c in clips]).astype(np.float32) - self.mean)
        k = min(self.k, self.x.shape[0])
        out = []
        for i in range(0, len(clips), 256):
            sims = q[i : i + 256] @ self.x.T
            out += [self._rank(row, k) for row in sims]
        return out

    def predict(self, clip):
        return self.predict_many([clip])[0]


def _as_ranked(pred):
    """Normalise a model output into [(gloss, confidence), ...] best first."""
    if isinstance(pred, dict):
        if "gloss" in pred and "confidence" in pred:
            ranked = [(pred["gloss"], pred["confidence"])] + [tuple(a) for a in pred.get("top", pred.get("alternatives", []))]
        else:
            ranked = sorted(pred.items(), key=lambda kv: -float(kv[1]))
    elif isinstance(pred, (list, tuple)) and pred and isinstance(pred[0], (list, tuple)):
        ranked = list(pred)
    elif isinstance(pred, (list, tuple)) and len(pred) >= 2 and isinstance(pred[0], str):
        ranked = [(pred[0], pred[1])] + (list(pred[2]) if len(pred) > 2 else [])
    else:
        raise TypeError(f"unrecognised model prediction {pred!r}")
    return [(str(g), float(c)) for g, c in ranked]


class RealModel(Adapter):
    """Wraps a `signer_core.model` classifier with fit(xyz_clips, labels) and predict(xyz) (see README).

    Only used when signer_core.model exposes such a class; otherwise `--model auto` falls back to the baseline.
    """

    CANDIDATES = ("KnnClassifier", "KnnModel", "SignClassifier", "Classifier", "Model")

    def __init__(self, cls):
        self.cls, self.name = cls, f"signer_core.model.{cls.__name__}"

    @classmethod
    def probe(cls):
        try:
            import importlib

            mod = importlib.import_module("signer_core.model")
        except Exception:
            return None
        for n in cls.CANDIDATES:
            c = getattr(mod, n, None)
            if isinstance(c, type) and callable(getattr(c, "fit", None)) and callable(getattr(c, "predict", None)):
                return cls(c)
        return None

    def _mismatch(self, e):
        return EvalError(f"{self.name} does not match the adapter contract ({type(e).__name__}: {e}); "
                         "run with --model baseline or adapt RealModel in eval/run.py")

    def fit(self, train):
        try:
            self.m = self.cls()
            self.m.fit([c.xyz for c in train], [c.gloss for c in train])
        except Exception as e:
            raise self._mismatch(e) from e

    def predict(self, clip):
        try:
            return _as_ranked(self.m.predict(clip.xyz))
        except Exception as e:
            raise self._mismatch(e) from e


def pick_adapter(which: str) -> Adapter:
    if which == "baseline":
        return BaselineKnn()
    real = RealModel.probe()
    if real is None:
        print("note: signer_core.model has no fit/predict classifier; using the baseline kNN", file=sys.stderr)
        return BaselineKnn()
    return real


# --------------------------------------------------------------------------------------------- metrics
def _num(x):
    """JSON-safe float: NaN/inf -> None."""
    if x is None:
        return None
    x = float(x)
    return round(x, 6) if math.isfinite(x) else None


def _conf(x) -> float:
    x = float(x)
    return min(max(x, 0.0), 1.0) if math.isfinite(x) else 0.0  # NaN confidence = no confidence


def evaluate(clips, folds, adapter: Adapter, high, low, seed) -> tuple[list[dict], list[dict], list[float]]:
    """Run all folds. Returns (per-clip rows, per-fold stats, latencies in ms)."""
    rows, fold_stats, lat = [], [], []
    rng = np.random.default_rng(seed)
    for f in folds:
        test = [c for c in clips if c.unit in f["units"]]
        train = [c for c in clips if c.unit not in f["units"]]
        if not test:
            continue
        if not train:
            raise EvalError(f"fold {f['name']} has no training clips")
        adapter.fit(train)
        preds = adapter.predict_many(test)
        n_ok = 0
        for c, pred in zip(test, preds):
            ranked = _as_ranked(pred)
            glosses = [g for g, _ in ranked]
            conf = _conf(ranked[0][1]) if ranked else 0.0
            ok = bool(glosses[:1] == [c.gloss])
            n_ok += ok
            rows.append({
                "true": c.gloss, "pred": glosses[0] if glosses else None, "conf": conf, "source": c.source,
                "signer": c.signer, "top1": ok, "top3": c.gloss in glosses[:TOPK], "tier": contracts.tier_for(conf, high, low),
            })
        for i in rng.permutation(len(test))[:LATENCY_PER_FOLD]:  # time features + predict, one clip at a time
            fresh = Clip(test[i].xyz, test[i].gloss, test[i].signer, test[i].source)
            t0 = time.perf_counter()
            adapter.predict(fresh)
            lat.append((time.perf_counter() - t0) * 1000)
        fold_stats.append({
            "name": f["name"], "held_out": sorted(f"{s}:{g}" for s, g in f["units"]),
            "n_train": len(train), "n_test": len(test), "top1": _num(n_ok / len(test)),
        })
        print(f"  fold {f['name']}: train {len(train)} test {len(test)} top1 {n_ok / len(test):.3f}", file=sys.stderr)
    return rows, fold_stats, lat


def _mean(flags):
    return float(np.mean(flags)) if len(flags) else 0.0


def summarise(rows) -> dict:
    conf = np.array([r["conf"] for r in rows])
    confirmed = np.array([r["tier"] == "confirmed" for r in rows])
    abstain = np.array([r["tier"] == "none" for r in rows])
    top1 = np.array([r["top1"] for r in rows])
    per_class = {}
    for g in sorted({r["true"] for r in rows}):
        sel = [r["top1"] for r in rows if r["true"] == g]
        per_class[g] = {"n": len(sel), "top1": _num(_mean(sel))}
    per_source = {}
    for s in SOURCES:
        sel = [r for r in rows if r["source"] == s]
        if sel:
            per_source[s] = {"n": len(sel), "top1": _num(_mean([r["top1"] for r in sel])), "top3": _num(_mean([r["top3"] for r in sel]))}
    wrong = Counter((r["true"], r["pred"]) for r in rows if not r["top1"])
    bins, ece = [], 0.0
    for lo in np.arange(0.0, 1.0, 0.1):
        hi = lo + 0.1
        sel = (conf >= lo) & ((conf < hi) if hi < 0.99 else (conf <= 1.0))  # last bin includes 1.0
        acc = float(top1[sel].mean()) if sel.any() else None
        if sel.any():
            ece += sel.sum() * abs(acc - float(conf[sel].mean()))
        bins.append({"lo": round(float(lo), 1), "hi": round(float(hi), 1), "n": int(sel.sum()), "acc": _num(acc)})
    ece /= max(len(rows), 1)
    return {
        "top1": _num(_mean(top1)),
        "top3": _num(_mean([r["top3"] for r in rows])),
        "selective_acc": _num(_mean(top1[confirmed])),  # 0.0 when nothing is confirmed (see n_confirmed)
        "coverage": _num(_mean(confirmed)),
        "abstain_rate": _num(_mean(abstain)),
        "per_class": per_class,
        "per_source": per_source,
        "n_confirmed": int(confirmed.sum()),
        "calibration": bins,
        "ece": _num(ece),
        "top_confusions": [{"true": t, "pred": p, "n": n} for (t, p), n in wrong.most_common(10)],
    }


def run_loso(args) -> dict:
    data_dir = Path(args.data_dir)
    sources = [args.source] if args.source else list(SOURCES)
    if not data_dir.is_dir():
        raise EvalError(f"data dir {data_dir} not found")
    clips, load_info = load_clips(data_dir, sources)
    if not clips:
        raise EvalError(f"no clips found under {data_dir} for sources {sources} (own: landmarks/<signer>/<GLOSS>/*.npz, "
                        "popsign: popsign/landmarks/<GLOSS>/*.npz, glasses: glasses/<signer>/<GLOSS>/*.npz)")
    units = {c.unit for c in clips}
    if len(units) < 2:
        raise EvalError(f"LOSO needs at least 2 signers, found {len(units)}: {sorted(units)}")
    found = [s for s in SOURCES if any(c.source == s for c in clips)]
    folds = make_folds(clips, args.popsign_folds, args.seed)
    adapter = pick_adapter(args.model)
    high = args.conf_high if args.conf_high is not None else contracts.CONF_HIGH
    low = args.conf_low if args.conf_low is not None else contracts.CONF_LOW
    print(f"{len(clips)} clips, {len(units)} signers, {len(folds)} folds, sources {found}, model {adapter.name}", file=sys.stderr)

    rows, fold_stats, lat = evaluate(clips, folds, adapter, high, low, args.seed)
    if not rows:
        raise EvalError("no clips were evaluated")
    signers_by_source = {s: sorted({c.signer for c in clips if c.source == s}) for s in found}
    out = {
        "name": args.name,
        "protocol": "loso",
        "sources": found,
        "signers": [g for s in found for g in signers_by_source[s]],
        **summarise(rows),
        "latency_ms_p50": _num(np.median(lat)) if lat else None,
        "n_clips": len(rows),
        "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        # beyond CONTRACTS section 6 (additive)
        "model": adapter.name,
        "conf_high": high,
        "conf_low": low,
        "seed": args.seed,
        "n_skipped": load_info["n_skipped"],
        "signers_by_source": signers_by_source,
        "folds": fold_stats,
        "protocol_detail": (
            "Leave-one-signer-out: own/glasses signers are one fold each, PopSign signers are hashed into "
            f"{min(args.popsign_folds, len(signers_by_source.get('popsign', [])) or 1)} signer-disjoint folds (seed {args.seed}). "
            "Each fold trains on all clips of the other signers from all selected sources and tests on the held-out signers; "
            "every clip is tested once. Tiers: confirmed >= conf_high, tentative/unsure >= conf_low, else abstain."
        ),
    }
    if args.report:
        write_report(out, rows, Path(args.out).with_suffix(".png"))
    return out


def write_report(res: dict, rows: list[dict], png: Path) -> None:
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        print("warning: matplotlib not installed, skipping the --report PNG", file=sys.stderr)
        return
    fig, ax = plt.subplots(1, 3, figsize=(15, 4.6))
    pc = res["per_class"]
    names = sorted(pc, key=lambda g: (pc[g]["top1"] or 0))
    ax[0].barh(names, [pc[g]["top1"] or 0 for g in names], color="#3b6ea5")
    ax[0].set_xlim(0, 1)
    ax[0].set_title("Top-1 per class (LOSO)")
    ax[0].tick_params(axis="y", labelsize=7)
    conf = np.array([r["conf"] for r in rows])
    ok = np.array([r["top1"] for r in rows])
    ths = np.linspace(0, 0.99, 50)
    cov = [(conf >= t).mean() for t in ths]
    acc = [ok[conf >= t].mean() if (conf >= t).any() else np.nan for t in ths]
    ax[1].plot(ths, cov, label="coverage")
    ax[1].plot(ths, acc, label="selective accuracy")
    ax[1].axvline(res["conf_high"], color="grey", ls="--", lw=1)
    ax[1].set_xlabel("confidence threshold")
    ax[1].set_ylim(0, 1.02)
    ax[1].legend()
    ax[1].set_title("Selective prediction")
    b = [x for x in res["calibration"] if x["n"]]
    ax[2].plot([0, 1], [0, 1], color="grey", lw=1)
    ax[2].plot([(x["lo"] + x["hi"]) / 2 for x in b], [x["acc"] for x in b], "o-")
    ax[2].set_xlabel("confidence")
    ax[2].set_ylabel("accuracy")
    ax[2].set_title(f"Calibration (ECE {res['ece']})")
    fig.suptitle(f"{res['name']}: top1 {res['top1']:.3f}  top3 {res['top3']:.3f}  selective {res['selective_acc']:.3f}  "
                 f"coverage {res['coverage']:.3f}  n={res['n_clips']}  model={res['model']}")
    fig.tight_layout()
    png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(png, dpi=120)
    plt.close(fig)
    print(f"wrote {png}", file=sys.stderr)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Signer LOSO eval (CONTRACTS.md section 6)")
    ap.add_argument("--loso", action="store_true", help="leave-one-signer-out protocol (the only protocol)")
    ap.add_argument("--source", choices=SOURCES, help="only this source (default: every source that has clips)")
    ap.add_argument("--data-dir", default=os.environ.get("SIGNER_DATA_DIR", "data"), help="data root (default: $SIGNER_DATA_DIR or data)")
    ap.add_argument("--out", help="JSON output (default eval/results/<name>.json)")
    ap.add_argument("--name", help="result name (default: stem of --out, else 'loso')")
    ap.add_argument("--report", action="store_true", help="also write <out>.png (needs matplotlib)")
    ap.add_argument("--model", choices=("auto", "baseline"), default="auto")
    ap.add_argument("--popsign-folds", type=int, default=5, help="signer-disjoint PopSign folds (default 5)")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--conf-high", type=float, help="override SIGNER_CONF_HIGH")
    ap.add_argument("--conf-low", type=float, help="override SIGNER_CONF_LOW")
    args = ap.parse_args(argv)
    if not args.loso:
        ap.error("--loso is required (LOSO is the only protocol)")
    if args.popsign_folds < 1:
        ap.error("--popsign-folds must be >= 1")
    args.name = args.name or (Path(args.out).stem if args.out else "loso")
    args.out = args.out or str(Path(__file__).resolve().parent / "results" / f"{args.name}.json")
    try:
        res = run_loso(args)
    except EvalError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(res, indent=2, allow_nan=False) + "\n")
    print(f"wrote {out}: top1 {res['top1']} top3 {res['top3']} selective {res['selective_acc']} "
          f"coverage {res['coverage']} abstain {res['abstain_rate']} n={res['n_clips']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
