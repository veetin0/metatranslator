"""Tests for eval/run.py on synthetic landmark clips (tmp dir only; no network, no camera, no real data)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest

EVAL = Path(__file__).resolve().parent
sys.path.insert(0, str(EVAL))
sys.path.insert(0, str(EVAL.parent / "core"))

import run  # noqa: E402
from signer_core.vision.clip import save_clip  # noqa: E402

GLOSSES = ("HELLO", "WATER", "BOOK")
SEC_KEYS = {"name", "protocol", "sources", "signers", "top1", "top3", "selective_acc", "coverage", "abstain_rate",
            "per_class", "latency_ms_p50", "n_clips", "created"}


def _proto(gloss: str):
    rng = np.random.default_rng(abs(hash_str(gloss)) % 2**32)
    return rng.random((21, 3)) * 0.3, rng.normal(size=(21, 3)) * 0.05, rng.random((21, 3)) * 0.3


def hash_str(s: str) -> int:  # stable across processes (unlike hash())
    return sum((i + 1) * ord(c) for i, c in enumerate(s)) * 7919


def make_clip(gloss, rng, noise=0.01, t=24, nan_hand=False):
    left, drift, right = _proto(gloss)
    xyz = np.full((t, 75, 3), np.nan, dtype=np.float32)
    pose = np.zeros((33, 3), dtype=np.float32) + np.array([0.5, 0.4, 0.0], dtype=np.float32)
    pose[11], pose[12] = (0.6, 0.5, 0.0), (0.4, 0.5, 0.0)
    scale, shift = rng.uniform(0.9, 1.1), rng.uniform(-0.05, 0.05)
    for i in range(t):
        xyz[i, :33] = pose
        xyz[i, 33:54] = left + drift * (i / t) + rng.normal(size=(21, 3)) * noise
        xyz[i, 54:75] = right - drift * (i / t) + rng.normal(size=(21, 3)) * noise
    xyz = xyz * scale + shift
    if nan_hand:
        xyz[::2, 54:75] = np.nan
        xyz[:3, 33:54] = np.nan
    return xyz


def write_data(root: Path, own_signers=("s1", "s2", "s3"), popsign_signers=(), per=6, seed=0, nan_clip=False):
    rng = np.random.default_rng(seed)
    n = 0
    for s in own_signers:
        for g in GLOSSES:
            for k in range(per):
                xyz = make_clip(g, rng, nan_hand=nan_clip and k == 0)
                save_clip(root / "landmarks" / s / g / f"{k}.npz", xyz, np.arange(len(xyz)) * 33, 30.0, g, s, "own")
                n += 1
    for s in popsign_signers:
        for g in GLOSSES:
            for k in range(per):
                xyz = make_clip(g, rng)
                save_clip(root / "popsign" / "landmarks" / g / f"{s}_{k}.npz", xyz, np.arange(len(xyz)) * 33, 30.0, g, s, "popsign")
                n += 1
    return n


def run_cli(tmp_path, *extra, name="t"):
    out = tmp_path / "res" / f"{name}.json"
    # --model baseline first: tests exercise the harness, not whatever signer_core.model currently exports
    code = run.main(["--loso", "--model", "baseline", "--data-dir", str(tmp_path / "data"), "--out", str(out), *extra])
    return code, out


def test_end_to_end_own(tmp_path):
    n = write_data(tmp_path / "data")
    code, out = run_cli(tmp_path)
    assert code == 0
    d = json.loads(out.read_text())  # strict JSON: allow_nan=False on write
    assert SEC_KEYS <= set(d)
    assert d["name"] == "t" and d["protocol"] == "loso" and d["sources"] == ["own"]
    assert d["signers"] == ["s1", "s2", "s3"] and d["n_clips"] == n == 54
    for k in ("top1", "top3", "selective_acc", "coverage", "abstain_rate"):
        assert 0 <= d[k] <= 1, k
    assert d["top3"] >= d["top1"] >= 0.9  # separable synthetic classes
    assert set(d["per_class"]) == set(GLOSSES)
    assert all(v["n"] == 18 and 0 <= v["top1"] <= 1 for v in d["per_class"].values())
    assert d["latency_ms_p50"] is not None and d["latency_ms_p50"] > 0
    assert d["created"].startswith("20") and len(d["folds"]) == 3
    assert d["coverage"] + d["abstain_rate"] <= 1.0 + 1e-9
    assert d["model"] in ("baseline-knn",) or d["model"].startswith("signer_core.model")


def test_own_and_popsign_sources(tmp_path):
    data = tmp_path / "data"
    n = write_data(data, popsign_signers=("p1", "p2", "p3", "p4", "p5", "p6", "p7"))
    code, out = run_cli(tmp_path, "--popsign-folds", "3")
    assert code == 0
    d = json.loads(out.read_text())
    assert d["sources"] == ["own", "popsign"] and d["n_clips"] == n
    assert set(d["signers"]) == {"s1", "s2", "s3"} | {f"p{i}" for i in range(1, 8)}
    assert len(d["folds"]) == 3 + 3  # 3 own signers + 3 popsign folds
    assert set(d["per_source"]) == {"own", "popsign"}
    assert d["model"] == "baseline-knn"
    # --source filters
    code, out2 = run_cli(tmp_path, "--source", "popsign", name="pop")
    d2 = json.loads(out2.read_text())
    assert code == 0 and d2["sources"] == ["popsign"] and d2["n_clips"] == 7 * 18


def test_folds_are_signer_disjoint_and_deterministic(tmp_path):
    write_data(tmp_path / "data", popsign_signers=tuple(f"p{i}" for i in range(23)))
    clips, _ = run.load_clips(tmp_path / "data", run.SOURCES)
    f1 = run.make_folds(clips, 5, seed=0)
    f2 = run.make_folds(clips, 5, seed=0)
    assert [sorted(f["units"]) for f in f1] == [sorted(f["units"]) for f in f2]
    seen = [u for f in f1 for u in f["units"]]
    assert len(seen) == len(set(seen)) == 3 + 23  # every signer in exactly one fold
    sizes = [len(f["units"]) for f in f1 if f["name"].startswith("popsign")]
    assert len(sizes) == 5 and max(sizes) - min(sizes) <= 1
    # same signer id in two sources stays two different units
    assert ("own", "s1") != ("popsign", "s1")


def test_deterministic(tmp_path):
    write_data(tmp_path / "data", popsign_signers=("p1", "p2", "p3"))
    _, a = run_cli(tmp_path, name="a")
    _, b = run_cli(tmp_path, name="b")
    da, db = json.loads(a.read_text()), json.loads(b.read_text())
    for d in (da, db):
        for k in ("created", "latency_ms_p50", "name"):
            d.pop(k)
    assert da == db


def test_nan_landmarks_are_safe(tmp_path):
    write_data(tmp_path / "data", nan_clip=True)
    # a clip with no landmarks at all
    save_clip(tmp_path / "data/landmarks/s1/HELLO/blank.npz", np.full((10, 75, 3), np.nan), np.arange(10), 30.0, "HELLO", "s1", "own")
    code, out = run_cli(tmp_path)
    assert code == 0
    d = json.loads(out.read_text())
    assert d["n_clips"] == 55 and 0 <= d["top1"] <= 1


def test_tier_thresholds(tmp_path):
    write_data(tmp_path / "data")
    code, out = run_cli(tmp_path, "--conf-high", "1.5", "--conf-low", "1.2", name="strict")  # nothing can be confirmed
    d = json.loads(out.read_text())
    assert code == 0 and d["coverage"] == 0 and d["abstain_rate"] == 1 and d["selective_acc"] == 0 and d["n_confirmed"] == 0
    code, out = run_cli(tmp_path, "--conf-high", "0.0", "--conf-low", "0.0", name="lax")  # everything confirmed
    d = json.loads(out.read_text())
    assert d["coverage"] == 1 and d["abstain_rate"] == 0 and d["selective_acc"] == pytest.approx(d["top1"], abs=1e-5)


def test_errors(tmp_path, capsys):
    (tmp_path / "data").mkdir()
    assert run_cli(tmp_path)[0] == 2  # no clips
    assert "no clips found" in capsys.readouterr().err
    write_data(tmp_path / "data", own_signers=("s1",))
    code, out = run_cli(tmp_path)
    assert code == 2 and not out.exists()  # one signer: LOSO impossible
    assert "at least 2 signers" in capsys.readouterr().err
    assert run_cli(tmp_path, "--source", "glasses")[0] == 2  # no glasses clips


def test_missing_loso_flag_is_a_usage_error(tmp_path):
    with pytest.raises(SystemExit) as e:
        run.main(["--data-dir", str(tmp_path)])
    assert e.value.code == 2


def test_invalid_clip_is_skipped_and_counted(tmp_path):
    write_data(tmp_path / "data")
    bad = tmp_path / "data/landmarks/s1/HELLO/bad.npz"
    bad.write_bytes(b"not a clip")
    code, out = run_cli(tmp_path)
    d = json.loads(out.read_text())
    assert code == 0 and d["n_skipped"] == 1 and d["n_clips"] == 54


def test_baseline_ranking_and_nan_confidence():
    assert run._conf(float("nan")) == 0.0 and run._conf(2.0) == 1.0 and run._conf(-1) == 0.0
    assert run._num(float("nan")) is None and run._num(float("inf")) is None
    assert run._as_ranked({"A": 0.2, "B": 0.7}) == [("B", 0.7), ("A", 0.2)]
    assert run._as_ranked(("A", 0.9, [("B", 0.1)])) == [("A", 0.9), ("B", 0.1)]


def test_auto_model_falls_back_or_wraps():
    assert isinstance(run.pick_adapter("auto"), run.Adapter)
    assert isinstance(run.pick_adapter("baseline"), run.BaselineKnn)

    class Wrong:  # a classifier whose API does not match the adapter contract
        def fit(self, only_one_arg):
            pass

        def predict(self, xyz):
            return 5

    with pytest.raises(run.EvalError, match="adapter contract"):
        run.RealModel(Wrong).fit([run.Clip(np.zeros((2, 75, 3)), "A", "s", "own")])


def test_report_png(tmp_path):
    write_data(tmp_path / "data")
    code, out = run_cli(tmp_path, "--report")
    assert code == 0 and out.exists()  # without matplotlib --report only warns
    try:
        import matplotlib  # noqa: F401
    except ImportError:
        return
    assert out.with_suffix(".png").stat().st_size > 1000
