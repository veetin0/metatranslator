#!/usr/bin/env python3
"""Train the large-vocabulary BiGRU (data/VOCAB_LARGE.md, ~600 glosses) and write data/models/gru_large.pt.
data/models/gru.pt (the 24-sign demo model) is never touched.

    PYTHONPATH=core core/.venv/bin/python core/tools/train_large.py --eval --out eval/results/m6_large.json
    PYTHONPATH=core core/.venv/bin/python core/tools/train_large.py --final

Data: ASL Citizen poses for every gloss (data/asl_citizen_large), PopSign for the 24 core signs (capped per gloss to
limit imbalance), taught glasses reps (12x), WLASL for the core signs.
--eval holds out 20% of each ASL Citizen gloss (random, so optimistic: no signer ids), one signer-disjoint PopSign fold,
and scores all WLASL clips (never trained on) over the full large label set.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import re
import sys
import time
from multiprocessing import Pool
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "core"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import train_gru as tg  # noqa: E402
from signer_core.vision.clip import load_clip  # noqa: E402

DATA = REPO / "data"
CORE = ["HELLO", "BYE", "YES", "NO", "PLEASE", "THANKYOU", "WAIT", "FINISH", "POTTY", "WATER", "WHERE", "WHY",
        "WHO", "TIME", "BOOK", "LISTEN", "TALK", "HOME", "SICK", "HAPPY", "HELP", "QUESTION", "UNDERSTAND", "AGAIN"]


def vocab_large():
    g = []
    for line in (DATA / "VOCAB_LARGE.md").read_text().splitlines():
        c = [x.strip() for x in line.strip("|").split("|")]
        if len(c) >= 3 and re.fullmatch(r"[A-Z]+", c[0]) and c[2].isdigit():
            g.append(c[0])
    return sorted(set(g) | set(CORE))


def load_dir(pattern, vocab, prefix):
    out = []
    for p in sorted(DATA.glob(pattern)):
        c = load_clip(p)
        if c["gloss"] in vocab:
            out.append((c["xyz"], c["gloss"], prefix + c["signer"], p.name))
    return out


def held_out(name):
    return int(hashlib.sha1(name.encode()).hexdigest(), 16) % 5 == 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--eval", action="store_true")
    ap.add_argument("--final", action="store_true")
    ap.add_argument("--out")
    ap.add_argument("--epochs", type=int, default=18)
    ap.add_argument("--aug", type=int, default=4)
    ap.add_argument("--citizen-weight", type=int, default=3, help="aug multiplier for ASL Citizen clips")
    ap.add_argument("--pop-cap", type=int, default=150, help="max PopSign clips per gloss")
    ap.add_argument("--weight", type=int, default=12)
    ap.add_argument("--limit-glosses", type=int, default=0, help="smoke test: first N glosses only")
    a = ap.parse_args()
    t0 = time.time()
    vocab = vocab_large()
    if a.limit_glosses:
        vocab = sorted(set(vocab[: a.limit_glosses]) | set(CORE[:3]))
    classes = sorted(vocab)
    vs = set(classes)
    cz = load_dir("asl_citizen_large/landmarks/*/*.npz", vs, "cz:")
    _, pop_all, taught = tg.load_all()
    pop_all = [c for c in pop_all if c[1] in vs]
    taught = [c for c in taught if c[1] in vs]
    wl = [c for c in tg.load_wlasl(vs)]
    rng = np.random.default_rng(0)
    by = {}
    for c in pop_all:
        by.setdefault(c[1], []).append(c)
    pop = []
    for g, cs in by.items():
        idx = rng.permutation(len(cs))[: a.pop_cap] if len(cs) > a.pop_cap else range(len(cs))
        pop += [cs[i] for i in idx]
    print(f"{len(classes)} classes: {len(cz)} ASL Citizen, {len(pop)}/{len(pop_all)} PopSign, {len(taught)} taught, {len(wl)} WLASL", flush=True)
    pool = Pool(30)

    def fit(clips_cz, clips_pop, clips_taught, seed):
        allc = clips_pop + clips_cz + clips_taught
        w = [1] * len(clips_pop) + [a.citizen_weight] * len(clips_cz) + [a.weight] * len(clips_taught)
        X, Y = tg.build(pool, [c[:3] for c in allc], a.aug, seed=seed, weight=w)
        return tg.train(X, Y, classes, a.epochs)

    if a.eval:
        te_cz = [c for c in cz if held_out(c[3])]
        tr_cz = [c for c in cz if not held_out(c[3])]
        signers = sorted({c[2] for c in pop})
        te_s = {s for j, s in enumerate(sorted(signers, key=lambda s: hashlib.sha1(s.encode()).hexdigest())) if j % 5 == 0}
        te_pop = [c for c in pop_all if c[2] in te_s]
        tr_pop = [c for c in pop if c[2] not in te_s]
        net, mean, std = fit(tr_cz, tr_pop, taught, 0)
        res = {}
        P = tg.predict(net, mean, std, tg.clean(pool, te_cz))
        res["asl_citizen_heldout"] = tg.score(P, [c[1] for c in te_cz], classes)
        core_cz = [i for i, c in enumerate(te_cz) if c[1] in CORE]
        res["asl_citizen_heldout_core"] = tg.score(P[core_cz], [te_cz[i][1] for i in core_cz], classes)
        if te_pop:
            res["popsign_heldout_core"] = tg.score(tg.predict(net, mean, std, tg.clean(pool, te_pop)), [c[1] for c in te_pop], classes)
        if wl:
            res["wlasl_core"] = tg.score(tg.predict(net, mean, std, tg.clean(pool, wl)), [c[1] for c in wl], classes)
        for k, v in res.items():
            print(k, v, flush=True)
        if a.out:
            flat = {f"{k}_{m}": round(v[m], 4) for k, v in res.items() for m in ("top1", "top3")}
            Path(a.out).write_text(json.dumps({
                "name": Path(a.out).stem, "n_classes": len(classes), "n_citizen_train": len(tr_cz), "n_citizen_test": len(te_cz),
                "protocol": "20% of each ASL Citizen gloss held out (random, optimistic: no signer ids); PopSign signer-disjoint fold; WLASL never trained on",
                **flat, "detail": res, "created": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")}, indent=2))
    if a.final:
        import torch

        net, mean, std = fit(cz, pop, taught, 1)
        out = DATA / "models"
        out.mkdir(exist_ok=True)
        torch.save({"state": net.state_dict(), "mean": mean, "std": std, "classes": classes}, out / "gru_large.pt")
        print("saved", out / "gru_large.pt", f"({time.time() - t0:.0f}s)")
    print("done")


if __name__ == "__main__":
    main()
