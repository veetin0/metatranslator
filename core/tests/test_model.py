"""M1.1 model tests: synthetic landmark clips only (no camera, data files or network)."""
import numpy as np
import pytest

from signer_core.contracts import REST, tier_for
from signer_core.model import (KNNClassifier, Recognizer, Segmenter, build_classifier, is_up, load_dataset,
                               mirror, read_vocab, trim_active)
from signer_core.vision.clip import save_clip

GLOSSES = ["HELLO", "BYE", "WATER", "BOOK", "WHERE"]


def body(t):
    """(t, 75, 3) with pose shoulders/hips, both hands missing."""
    x = np.full((t, 75, 3), np.nan, np.float32)
    x[:, :33] = 0.5
    x[:, 0, :2] = (0.5, 0.3)
    x[:, 11, :2], x[:, 12, :2] = (0.6, 0.5), (0.4, 0.5)
    x[:, 13, :2], x[:, 14, :2] = (0.65, 0.7), (0.35, 0.7)
    x[:, 23, :2], x[:, 24, :2] = (0.58, 0.95), (0.42, 0.95)
    x[:, :33, 2] = 0.0
    return x


def sign_clip(cls, rng, t=30, noise=0.01, rest_pad=0):
    """A right-hand trajectory + hand shape that depends on the class index."""
    x = body(t + 2 * rest_pad)
    u = np.linspace(0, 1, t)
    a = 2 * np.pi * (cls + 1) / len(GLOSSES)
    wrist = np.stack([0.45 + 0.12 * np.cos(a + 3 * u * (cls % 3 + 1)), 0.55 - 0.15 * np.sin(a + 2 * u)], 1)
    shape = np.stack([np.cos(np.arange(21) * (cls + 1) * 0.6), np.sin(np.arange(21) * (cls + 2) * 0.4)], 1) * 0.04
    hand = wrist[:, None, :] + shape[None] + rng.normal(0, noise, (t, 21, 2))
    sl = slice(rest_pad, rest_pad + t)
    x[sl, 54:75, :2] = hand
    x[sl, 54:75, 2] = 0.0
    x[sl, 16, :2] = wrist  # pose right wrist follows
    return x


def dataset(n_per=8, seed=0, noise=0.01):
    rng = np.random.default_rng(seed)
    X, y = [], []
    for c, g in enumerate(GLOSSES):
        for _ in range(n_per):
            X.append(sign_clip(c, rng, t=int(rng.integers(20, 40)), noise=noise))
            y.append(g)
    return X, y


def test_knn_learns_synthetic_classes_with_top2():
    X, y = dataset(8, seed=0)
    clf = KNNClassifier().fit(X, y)
    Xt, yt = dataset(4, seed=1)
    preds = [clf.predict(x, top=3) for x in Xt]
    acc = np.mean([p[0][0] == g for p, g in zip(preds, yt)])
    assert acc >= 0.9, acc
    for p in preds:
        assert len(p) == 3 and p[0][1] >= p[1][1] >= p[2][1]
        assert all(0.0 <= c <= 1.0 for _, c in p)
    proba = clf.predict_proba(Xt[0])
    assert set(proba) == set(GLOSSES) and sum(proba.values()) <= 1.0 + 1e-6


def test_confident_on_known_and_low_on_novel():
    X, y = dataset(8, seed=0)
    clf = KNNClassifier().fit(X, y)
    known = [clf.predict(x)[0][1] for x in dataset(3, seed=2)[0]]
    assert np.median(known) >= 0.8, known
    rng = np.random.default_rng(5)
    junk = body(30)
    junk[:, 33:54, :2] = rng.uniform(0.0, 1.0, (30, 21, 2))  # random left-hand scribble
    junk[:, 33:54, 2] = 0.0
    assert clf.predict(junk)[0][1] < 0.5


def test_tiers_follow_contract_thresholds():
    assert tier_for(0.9) == "confirmed" and tier_for(0.6) == "unsure" and tier_for(0.2) == "none"


def test_mirror_is_involution_and_swaps_hands():
    x = sign_clip(1, np.random.default_rng(0))
    m = mirror(x)
    assert np.isnan(m[:, 54:75]).all() and not np.isnan(m[:, 33:54]).any()
    np.testing.assert_allclose(mirror(m), x, equal_nan=True, atol=1e-6)


def test_trim_active_drops_idle_frames():
    x = sign_clip(0, np.random.default_rng(0), t=20, rest_pad=10)
    assert len(trim_active(x)) == 20 + 4


def test_calibrate_add_remove_save_load(tmp_path):
    X, y = dataset(6, seed=0)
    clf = KNNClassifier().fit(X, y)
    Xv, yv = dataset(2, seed=3)
    t = clf.calibrate(Xv, yv)
    assert 0 < t <= 0.5
    n = len(clf.labels)
    clf.add(X[0], "TAUGHT")
    assert "TAUGHT" in clf.classes and clf.remove("TAUGHT") == 2 and len(clf.labels) == n
    path = clf.save(tmp_path / "knn.npz")
    back = KNNClassifier.load(path)
    a, b = back.predict(Xv[0]), clf.predict(Xv[0])
    assert [g for g, _ in a] == [g for g, _ in b]
    assert [c for _, c in a] == pytest.approx([c for _, c in b])


def stream(clips_with_rest):
    """Concatenate clips (already padded with rest frames) into one 30 fps frame stream."""
    frames = np.concatenate(clips_with_rest)
    return frames, (np.arange(len(frames)) * 33).astype(np.int64)


def test_segmenter_finds_each_sign_between_rests():
    rng = np.random.default_rng(0)
    frames, ts = stream([sign_clip(c, rng, t=30, rest_pad=15) for c in (0, 2, 4)])
    seg = Segmenter()
    out = [s for f, t in zip(frames, ts) if (s := seg.push(f, int(t))) is not None]
    tail = seg.flush()
    out += [tail] if tail else []
    assert len(out) == 3
    for s in out:
        assert 25 <= len(s.xyz) <= 40 and s.duration_ms >= 250
    assert not is_up(body(1)[0])


def test_segmenter_cuts_long_signing_and_ignores_blips():
    rng = np.random.default_rng(0)
    seg = Segmenter(max_ms=1000)
    long_clip = sign_clip(0, rng, t=90)
    cuts = [s for i, f in enumerate(long_clip) if (s := seg.push(f, i * 33)) is not None]
    assert len(cuts) >= 2 and all(c.duration_ms <= 1000 for c in cuts)
    seg = Segmenter()
    blip = sign_clip(0, rng, t=3, rest_pad=20)
    assert all(seg.push(f, i * 33) is None for i, f in enumerate(blip)) and seg.flush() is None


def test_recognizer_emits_predictions_and_drops_rest():
    X, y = dataset(8, seed=0)
    rest = [body(25) for _ in range(4)]
    for r in rest:  # REST prototype: hand low at the hips
        r[:, 54:75, :2] = np.random.default_rng(1).normal((0.45, 1.0), 0.01, (25, 21, 2))
        r[:, 54:75, 2] = 0
    clf = KNNClassifier().fit(X + rest, y + [REST] * 4)
    rng = np.random.default_rng(7)
    frames, ts = stream([sign_clip(c, rng, t=30, rest_pad=15) for c in (1, 3)])
    rec = Recognizer(clf)
    preds = [p for f, t in zip(frames, ts) if (p := rec.push(f, int(t))) is not None]
    tail = rec.flush()
    preds += [tail] if tail else []
    assert [p.gloss for p in preds] == ["BYE", "BOOK"]
    for p in preds:
        assert p.tier == tier_for(p.confidence) and p.end_ms > p.start_ms
        assert all(g != REST for g, _ in p.alternatives) and len(p.alternatives) <= 2


def test_load_dataset_and_build_classifier_from_files(tmp_path):
    rng = np.random.default_rng(0)
    (tmp_path / "VOCAB.md").write_text("| GLOSS | english | source | popsign_name |\n"
                                       "| HELLO | hello | popsign | hello |\n| BYE | bye | popsign | bye |\n")
    for c, g in enumerate(GLOSSES[:3]):  # WATER is not in this vocab -> filtered
        for i in range(3):
            x = sign_clip(c, rng)
            t = np.arange(len(x), dtype=np.int64) * 33
            save_clip(tmp_path / "popsign" / "landmarks" / g / f"p{i}.npz", x, t, 30.0, g, f"ps{i}", "popsign")
            save_clip(tmp_path / "landmarks" / "s1" / g / f"{i}.npz", x, t, 30.0, g, "s1", "own")
    assert read_vocab(tmp_path / "VOCAB.md") == ["HELLO", "BYE"]
    ds = load_dataset(tmp_path, ("own", "popsign"), vocab=["HELLO", "BYE"])
    assert len(ds) == 12 and set(ds.source) == {"own", "popsign"} and set(ds.gloss) == {"HELLO", "BYE"}
    assert len(load_dataset(tmp_path, ("own",), exclude_signers=["s1"])) == 0
    clf = build_classifier(str(tmp_path))
    assert clf.classes == ["BYE", "HELLO"]
    with pytest.raises(FileNotFoundError):
        build_classifier(str(tmp_path / "empty"))
