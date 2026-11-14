#!/usr/bin/env python3
"""Train a temporal classifier (BiGRU) on landmark clips and compare it with the kNN.

    PYTHONPATH=core core/.venv/bin/python core/tools/train_gru.py --cv 2        # signer-disjoint folds of PopSign
    PYTHONPATH=core core/.venv/bin/python core/tools/train_gru.py --taught      # PopSign only -> test on taught glasses reps
    PYTHONPATH=core core/.venv/bin/python core/tools/train_gru.py --final       # PopSign + taught -> data/models/gru.pt

Taught glasses reps (data/taught/<GLOSS>_G/*.npz) count as the base gloss (HELLO_G -> HELLO).
Augmentation (landmark level, before features): in-plane rotation, scale, shift, mirror, speed, jitter, dropped hands.
"""
from __future__ import annotations

import argparse
import hashlib
import sys
import time
from multiprocessing import Pool
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "core"))

from signer_core.model.gru import make_model  # noqa: E402
from signer_core.model import KNNClassifier, mirror, read_vocab, trim_active  # noqa: E402
from signer_core.vision.clip import load_clip  # noqa: E402
from signer_core.vision.features import FEATURE_DIM, clip_features  # noqa: E402

DATA = REPO / "data"


def load_all():
    vocab = [g for g in read_vocab(str(DATA / "VOCAB.md")) if g != "REST"]
    pop = []
    for p in sorted(DATA.glob("popsign/landmarks/*/*.npz")):
        try:
            c = load_clip(p)
        except ValueError:
            continue
        if c["gloss"] in vocab:
            pop.append((c["xyz"], c["gloss"], c["signer"]))
    taught = []
    for p in sorted(DATA.glob("taught/*/*.npz")):
        try:
            c = load_clip(p)
        except ValueError:  # taught reps keep wall-clock stamps that can repeat
            z = np.load(p, allow_pickle=True)
            c = {"xyz": z["xyz"]}
        g = p.parent.name.removesuffix("_G")
        if g in vocab:
            taught.append((c["xyz"], g, "glasses"))
    return vocab, pop, taught


def augment(xyz, rng):
    x = np.asarray(xyz, dtype=np.float32).copy()
    if rng.random() < 0.5:
        x = mirror(x)
    ang = np.deg2rad(rng.uniform(-12, 12))
    s = rng.uniform(0.88, 1.12)
    shift = rng.uniform(-0.05, 0.05, size=2)
    c, sn = np.cos(ang), np.sin(ang)
    xy = x[..., :2] - 0.5
    x[..., 0] = 0.5 + s * (c * xy[..., 0] - sn * xy[..., 1]) + shift[0]
    x[..., 1] = 0.5 + s * (sn * xy[..., 0] + c * xy[..., 1]) + shift[1]
    x[..., 2] *= s
    x += rng.normal(0, 0.004, x.shape).astype(np.float32)
    T = len(x)
    if T > 6:  # speed change by resampling the time axis
        n = max(6, int(T * rng.uniform(0.8, 1.25)))
        idx = np.linspace(0, T - 1, n).round().astype(int)
        x = x[idx]
        drop = rng.random(len(x)) < 0.05  # whole frames lose their hands
        x[drop, 33:75] = np.nan
    return x


def feats(xyz):
    return clip_features(trim_active(xyz)).astype(np.float32)


def _aug_job(args):
    xyz, seed = args
    return feats(augment(xyz, np.random.default_rng(seed)))


def _clean_job(xyz):
    return feats(xyz)


def build(pool, clips, n_aug, seed=0, weight=None):
    X, Y = [], []
    jobs, ys = [], []
    for i, (xyz, g, _s) in enumerate(clips):
        reps = n_aug * (weight[i] if weight is not None else 1)
        for k in range(reps):
            jobs.append((xyz, seed * 1_000_003 + i * 101 + k))
            ys.append(g)
    X = np.stack(pool.map(_aug_job, jobs, chunksize=64))
    return X, np.array(ys)


def clean(pool, clips):
    return np.stack(pool.map(_clean_job, [c[0] for c in clips], chunksize=64))


def train(X, Y, classes, epochs=18, seed=0):
    import torch
    import torch.nn.functional as F

    torch.manual_seed(seed)
    dev = "mps" if torch.backends.mps.is_available() else "cpu"
    mean, std = X.reshape(-1, FEATURE_DIM).mean(0), X.reshape(-1, FEATURE_DIM).std(0) + 1e-3
    Xt = torch.tensor((X - mean) / std, dtype=torch.float32)
    yt = torch.tensor([classes.index(g) for g in Y])
    net = make_model(len(classes)).to(dev)
    opt = torch.optim.AdamW(net.parameters(), lr=2e-3, weight_decay=1e-2)
    steps = epochs * ((len(Xt) + 255) // 256)
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=3e-3, total_steps=steps)
    for ep in range(epochs):
        net.train()
        perm = torch.randperm(len(Xt))
        tot = 0.0
        for i in range(0, len(Xt), 256):
            b = perm[i:i + 256]
            loss = F.cross_entropy(net(Xt[b].to(dev)), yt[b].to(dev), label_smoothing=0.1)
            opt.zero_grad(); loss.backward(); opt.step(); sched.step()
            tot += float(loss) * len(b)
        print(f"  epoch {ep + 1}/{epochs} loss {tot / len(Xt):.3f}", flush=True)
    net.eval().cpu()
    return net, mean, std


def predict(net, mean, std, X):
    import torch

    with torch.no_grad():
        return torch.softmax(net(torch.tensor((X - mean) / std, dtype=torch.float32)), dim=1).numpy()


def score(P, y, classes):
    yi = np.array([classes.index(g) for g in y])
    top3 = np.argsort(-P, axis=1)[:, :3]
    conf = P.max(1)
    hit = P.argmax(1) == yi
    conf_hi = conf >= 0.8
    return {"top1": float(hit.mean()), "top3": float((top3 == yi[:, None]).any(1).mean()),
            "cov@0.8": float(conf_hi.mean()), "acc@0.8": float(hit[conf_hi].mean()) if conf_hi.any() else float("nan")}


def folds_of(pop, k):
    signers = sorted({s for _, _, s in pop})
    order = sorted(signers, key=lambda s: hashlib.sha1(f"0:{s}".encode()).hexdigest())
    return [{s for j, s in enumerate(order) if j % k == i} for i in range(k)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cv", type=int, default=0, help="number of PopSign folds to run (of 5)")
    ap.add_argument("--taught", action="store_true")
    ap.add_argument("--final", action="store_true")
    ap.add_argument("--taughtcv", type=int, default=0, help="hold out every n-th taught rep, train on PopSign + the rest")
    ap.add_argument("--weight", type=int, default=12)
    ap.add_argument("--out", help="write the pooled cv result as eval/results-style JSON")
    ap.add_argument("--aug", type=int, default=4)
    ap.add_argument("--epochs", type=int, default=18)
    args = ap.parse_args()
    vocab, pop, taught = load_all()
    classes = sorted(vocab)
    print(f"{len(pop)} PopSign clips, {len(taught)} taught glasses reps, {len(classes)} classes", flush=True)
    pool = Pool(8)
    t0 = time.time()
    if args.cv:
        folds = folds_of(pop, 5)
        allP, ally = [], []
        for fi in range(args.cv):
            tr = [c for c in pop if c[2] not in folds[fi]]
            te = [c for c in pop if c[2] in folds[fi]]
            X, Y = build(pool, tr, args.aug)
            net, mean, std = train(X, Y, classes, args.epochs)
            P = predict(net, mean, std, clean(pool, te))
            allP.append(P); ally += [c[1] for c in te]
            r = score(P, [c[1] for c in te], classes)
            print(f"fold{fi}: GRU {r}  ({time.time() - t0:.0f}s)  [kNN baseline top1 ~0.51]", flush=True)
        if args.out:
            import datetime, json
            r = score(np.concatenate(allP), ally, classes)
            r.update(name=Path(args.out).stem, protocol="loso-5fold-signer-disjoint", model="signer_core.model.gru.GRUClassifier",
                     n_clips=len(ally), n_folds=args.cv, top1_per_fold=None, conf_high=0.8, aug=args.aug, epochs=args.epochs,
                     created=datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"))
            Path(args.out).write_text(json.dumps(r, indent=2))
            print("wrote", args.out, r, flush=True)
    if args.taught and taught:
        X, Y = build(pool, pop, args.aug)
        net, mean, std = train(X, Y, classes, args.epochs)
        yt = [c[1] for c in taught]
        print("taught reps, PopSign-only GRU:", score(predict(net, mean, std, clean(pool, taught)), yt, classes))
        knn = KNNClassifier().fit([c[0] for c in pop], [c[1] for c in pop])
        P = np.array([[dict(knn.predict_proba(c[0])).get(g, 0.0) for g in classes] for c in taught])
        print("taught reps, PopSign-only kNN:", score(P, yt, classes), flush=True)
    if args.taughtcv:
        order = {}
        idx = [order.setdefault(g, []).append(i) or len(order[g]) - 1 for i, (_, g, _s) in enumerate(taught)]
        for hold in range(args.taughtcv):
            te = [c for c, k in zip(taught, idx) if k % args.taughtcv == hold]
            trn = [c for c, k in zip(taught, idx) if k % args.taughtcv != hold]
            X, Y = build(pool, pop + trn, args.aug, seed=2, weight=[1] * len(pop) + [args.weight] * len(trn))
            net, mean, std = train(X, Y, classes, args.epochs)
            print(f"taught holdout {hold} (n={len(te)}), PopSign + other glasses reps:",
                  score(predict(net, mean, std, clean(pool, te)), [c[1] for c in te], classes), flush=True)
    if args.final:
        weight = None
        allc = pop + taught
        weight = [1] * len(pop) + [args.weight] * len(taught)  # glasses reps count 12x: the stage view matters most
        X, Y = build(pool, allc, args.aug, seed=1, weight=weight)
        net, mean, std = train(X, Y, classes, args.epochs)
        import torch

        out = DATA / "models"
        out.mkdir(exist_ok=True)
        torch.save({"state": net.state_dict(), "mean": mean, "std": std, "classes": classes}, out / "gru.pt")
        print("saved", out / "gru.pt", f"({time.time() - t0:.0f}s)")


if __name__ == "__main__":
    main()
