# eval/ - Signer LOSO evaluation (CONTRACTS.md section 6)

`eval/run.py` measures the sign classifier on held-out signers. **Every accuracy number in the deck, README and pitch
comes only from the JSON files in `eval/results/`** (never from a notebook, a live demo run or memory).

## Run

```bash
# repo root; needs numpy (core/.venv or any Python >= 3.10 with numpy), matplotlib only for --report
python eval/run.py --loso --out eval/results/m1.json            # all sources that have clips
python eval/run.py --loso --source own --out eval/results/own.json --report
python eval/run.py --loso --source popsign --popsign-folds 5
python eval/run.py --loso --source glasses --out eval/results/glasses.json   # M2, glasses camera
python -m pytest eval/test_run.py -q -p no:cacheprovider        # synthetic data in a tmp dir; no camera, no network
```

Flags: `--data-dir data` (or `SIGNER_DATA_DIR`), `--model auto|baseline`, `--popsign-folds 5`, `--seed 0`,
`--conf-high/--conf-low` (default `signer_core.contracts.CONF_HIGH/LOW` = `SIGNER_CONF_HIGH/LOW` = 0.80 / 0.50),
`--name` (default: stem of `--out`). Exit code 2 with a message when no clips are found, the data dir is missing,
or fewer than 2 signers exist. Invalid `.npz` files are skipped, warned about, and counted in `n_skipped`.
Runtime on ~2600 synthetic clips: about 4 s.

Inputs (CONTRACTS section 5): own `data/landmarks/<signer>/<GLOSS>/*.npz`, PopSign `data/popsign/landmarks/<GLOSS>/*.npz`,
glasses `data/glasses/<signer>/<GLOSS>/*.npz`. Clips are read with `signer_core.vision.clip.load_clip` (validated).

## Protocol

Leave-one-signer-out. A signer is identified by `(source, signer id)`, so own `s1` and a PopSign `s1` are different people.

* Own and glasses signers: one fold each (the held-out signer is never in training).
* PopSign signers: sorted by `sha1(seed:id)` and dealt round-robin into `--popsign-folds` (5) signer-disjoint folds,
  so runtime stays small with hundreds of signers. Deterministic for a given seed.
* Per fold: fit on **all clips of all other signers from all selected sources** (so the model sees own + PopSign like the
  live system does), predict every held-out clip. Each clip is tested exactly once; `n_clips` is the number tested.
* A class that never appears in a fold's training set can only be counted wrong.
* Tiers use `signer_core.contracts.tier_for`: `confirmed` if confidence >= 0.80, `unsure` (tentative) if >= 0.50, else
  abstain (`none`).

## Output (`eval/results/<name>.json`)

CONTRACTS section 6 keys: `name, protocol ("loso"), sources, signers, top1, top3, selective_acc, coverage,
abstain_rate, per_class {GLOSS: {n, top1}}, latency_ms_p50, n_clips, created`.

* `top1` / `top3`: over all tested clips (top-3 = true gloss in the model's three best).
* `selective_acc`: accuracy on `confirmed` predictions; `coverage`: share predicted `confirmed`; `abstain_rate`: share
  below `conf_low`. If nothing is confirmed `selective_acc` is 0.0 and `n_confirmed` is 0 (check `coverage` first).
* `latency_ms_p50`: median wall time of one clip, feature extraction + predict, over a seeded sample of 30 clips per fold.
  It excludes landmark extraction (MediaPipe); quote it as "classifier latency".

Additive keys: `model`, `conf_high`, `conf_low`, `seed`, `n_skipped`, `signers_by_source`, `folds` (held-out signers,
sizes, top1 per fold), `protocol_detail`, `per_source` (top1/top3 per source), `n_confirmed`, `calibration` (10 confidence
bins: n and accuracy), `ece`, `top_confusions`. `--report` writes `eval/results/<name>.png` (per-class top-1, coverage vs
selective accuracy, calibration) when matplotlib is installed; otherwise it warns and skips.

## Model adapter

`run.py` talks to a classifier through `Adapter` (`fit(train_clips)`, `predict(clip) -> [(gloss, confidence), ...]` best first).

* **Baseline** (`--model baseline`, and the `auto` fallback): `BaselineKnn`, cosine kNN on `flat_features` (32 x 180) centred on the
  train mean, k = 5, vote weight `1 / (1 - cos + 1e-3)`, confidence = class share of the vote.
* **Real model** (`--model auto`): if `signer_core.model` exports a class named `KnnClassifier`, `KnnModel`, `SignClassifier`,
  `Classifier` or `Model` with a no-argument constructor, `fit(list_of_xyz, list_of_gloss)` and `predict(xyz)` returning
  `[(gloss, conf), ...]`, `{gloss: prob}` or `(gloss, conf, [(gloss, conf), ...])`, it is used. Otherwise a note is printed and
  the baseline runs. The JSON `model` field says which one produced the numbers; **check it before quoting a number**.
  To point the harness at the real M1.1 model, adapt `RealModel` (about 10 lines) to its actual API.

## Feeding the deck

1. Run `python eval/run.py --loso --out eval/results/m1.json --report` on the real data (D6 needs `own` and `popsign` in
   `sources` and `n_clips >= 1000`).
2. Commit the JSON and PNG. Never commit results produced from synthetic data.
3. Pitch/deck numbers = `top1`, `top3`, `selective_acc` with `coverage`, and `latency_ms_p50` from that file. State the protocol
   (LOSO, held-out signers), the model, the number of signers and clips. Quote `selective_acc` together with `coverage`.
