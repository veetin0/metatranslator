# Gap check: ASL recognition stack vs OBJECTIVE (section 3 + engineering constraints)

Mission m-669ad, branch crew/topias/m-669ad, 2026-11-13. Read-only review of code at commit 6ce9c52.
Targets: `challenge/prompts/OBJECTIVE.md` (DIRECTIVES #14), PLAN.md, CONTRACTS.md, M1/M2 contracts.

## What was and was not measured
- `eval/results/m1.json` is **not in this checkout** (`eval/results/` holds only `.gitkeep`; no commit ever added a result). `data/landmarks/` and `data/popsign/landmarks/` do not exist here either, so I could not run anything. The lead's numbers (PopSign LOSO v0 kNN: top1 0.551, top3 0.803, selective_acc 0.939 at coverage 0.116, 25 classes) are **taken as given and unverified by me**.
- Confusions HAPPY->PLEASE and TALK->WATER also come from the lead. I have no per-class or `top_confusions` data. `eval/run.py` already writes `per_class` and `top_confusions`, so the full picture exists in the m1.json that sits on the lead's machine.
- Unmeasured anywhere: own-clip accuracy, glasses-camera accuracy, end-to-end latency, live-segmenter accuracy (all eval is on pre-cut clips, not on the segmenter output), any LSTM/GRU number.
- The PopSign paper figure "LSTM 84.2 % on 250 classes" (`research/sign-recognition.md:10`) is a literature number from a different protocol and class count. It does not transfer to our 20-ish-class kNN and I do not use it as a target.

## 1. Point-by-point vs OBJECTIVE

| # | Objective point | Status | Evidence |
|---|---|---|---|
| 1 | MediaPipe Holistic for hands + face + body | **PARTIAL** | Holistic is used: `core/signer_core/vision/holistic.py:55-66` (`HolisticLandmarker`, VIDEO mode). Hands and pose are kept. **Face is dropped**: `output_face_blendshapes=False` (`holistic.py:69`), and the stored layout is 75 points, pose+hands only (`vision/landmarks.py:6`, CONTRACTS §5). Face reaches no classifier. The question-flag/face graft is only planned (PLAN M3.2, `vision/face.py` does not exist). |
| 2 | PyTorch temporal classifier | **MISSING** | No `torch` import anywhere in `core/` or `eval/`; `core/pyproject.toml:9-17` has no torch dependency. (DECISION.md:47 lists torch as "have", INVENTORY.md:16 says it is installed on the lead's machine, but no code uses it.) |
| 3 | LSTM as initial baseline | **MISSING** | Nothing named LSTM/GRU in code. PLAN M2.2 and M2 contract task "GRU vs kNN" are `todo`. The shipped model is a kNN (`model/knn.py:47-197`), which the objective did not ask for. |
| 4 | 10-20 signs/phrases | **PARTIAL** | We have 24 signs + REST (`data/VOCAB.md`, CONTRACTS §0/§5, `/health.vocab:24`). That is over the 10-20 limit by 4. 20 of 24 come from PopSign; 4 (HELP, QUESTION, UNDERSTAND, AGAIN) need own recordings that do not exist in this checkout. |
| 5 | Confidence scores | **MATCHES** | `KNNClassifier.predict_proba` returns a calibrated per-class confidence = distance-weighted vote share x novelty factor (`knn.py:158-181`); `Prediction.confidence` (`model/recognizer.py:14-25`). `calibrate()` tunes the vote temperature on held-out clips (`knn.py:128-137`). Eval reports `ece` and `calibration` bins (`eval/README.md` additive keys). |
| 6 | Reject low confidence, do not invent | **MATCHES** | Tiers `confirmed >= 0.80`, `unsure >= 0.50`, else `none` (`contracts.py:25-36`). Only `confirmed` is spoken (CONTRACTS §4 `speak`). Signs under `unsure` are dropped from a phrase and an empty phrase becomes "Didn't catch that" (`relay/pipeline.py:6-9`). The novelty factor pushes unfamiliar motion towards 0 (`knn.py:106-121`). Cost: coverage 0.116 at selective_acc 0.939 means about 88 % of clips are not confirmed; see section 3. |
| 7 | Evaluate pretrained model/dataset before custom training | **PARTIAL** | Dataset evaluated first: PopSign v1.0 chosen and run through our own Holistic (DECISION.md:51, `core/tools/get_popsign.py`, `extract_landmarks.py`), with LOSO eval (`eval/run.py`). **No pretrained model was ever run.** research/sign-recognition.md:48 lists a PopSign/GISLR pretrained LSTM as "Fallback A" only; not evaluated, and Kaggle `asl-signs` is out per directive 10. So "dataset first" holds, "pretrained model first" is unmet. Kaggle-hosted weights are probably unreachable anyway; I did not check other hosts (unmeasured). |
| 8 | Avoid training a large net from scratch | **MATCHES** | Nothing is trained but a kNN index; any LSTM we add at ~20 classes x 75-point features is small (CPU seconds-minutes; unmeasured). |
| 9 | Preserve temporal information | **PARTIAL** | The clip is resampled to 32 steps and flattened to 32 x 180 (`vision/features.py:119-150`), so frame order is baked into the vector and a cosine kNN compares positionally (`knn.py:98-100`). There is no dynamic alignment (DTW) or recurrent state, so speed/phase variation between signers hurts it. No evidence on how much; the 0.551 top1 is consistent with this but not proof. |
| 10 | Facial expressions + body landmarks "where possible" | **PARTIAL** | Body: pose points nose/shoulders/elbows/wrists are in the features (`features.py:34`, `POSE_KEEP`). Face: none (see row 1). |
| 11 | Clearly indicate uncertain predictions | **MATCHES** | `unsure` tier with top-2 alternatives (`Prediction.alternatives`, `recognizer.py:27-31`); caption event carries `tier`, `alternatives` (CONTRACTS §4); lens renders amber "?" (PLAN M1.3). |
| 12 | Modular so the model can be replaced | **PARTIAL** | Duck-typed seam exists: `Recognizer(classifier)` needs only `predict(xyz, top) -> [(gloss, conf)]` (`recognizer.py:19-22,35-39`); eval has an `Adapter` (`eval/run.py:119-135`). But: `build_classifier` hard-wires `KNNClassifier` and returns it by name (`recognizer.py:62-70`); `SIGNER_MODEL` is only echoed into `/health` (`relay/app.py:98`), it selects nothing; `eval/run.py:RealModel.probe` finds a class by guessing names (`CANDIDATES` at `run.py:214`, so a `GRUClassifier` would NOT be picked up as `auto`); no Protocol/registry, no save/load contract beyond kNN's own `save/load` (`knn.py:177-197`). |
| 13 | Pipeline: video -> OpenCV -> Holistic -> classifier | **MATCHES (differs in shape)** | OpenCV decode + Holistic per frame in `relay/pipeline.py:21-52`; live webcam in `sources/webcam.py`. Ours is a streaming WS pipeline with a segmenter (`model/segmenter.py`), whereas the objective describes upload-after-stop and says avoid streaming. The recognizer itself is chunk-agnostic; `Recognizer.flush()` on Stop gives the same result for an uploaded clip. Not a recognition gap; noting it so nobody thinks the classifier assumes live input. |
| 14 | Gemini translation / Gemini TTS | out of scope here | Language layer is templates + optional Claude Haiku (`language/template.py`, PLAN M3.2). Flagged for whoever owns the objective gap on translation. |

Score (rows 1-13): MATCHES 5 (5, 6, 8, 11, 13), PARTIAL 6 (1, 4, 7, 9, 10, 12), MISSING 2 (2, 3); row 14 out of scope.

## 2. Where recognition is weakest, and why that matters

1. **The accuracy number is not demo-grade.** top1 0.551 over 25 classes (lead's number) means roughly every second sign is wrong if forced. The system survives only through rejection: coverage 0.116 means about 1 in 9 attempts is shown as confirmed. For the objective's "works reliably during a live demonstration" that is the main risk. A live signer repeating a phrase will usually get "Didn't catch that" or "?".
2. **Confusions are between sign pairs that share location and motion** (HAPPY/PLEASE: flat hand circling on the chest; TALK/WATER: hand near the mouth). A positional cosine kNN on handshape+path cannot separate these, and pose-only face-free features give no mouth cue. Only a model that sees handshape over time (or those pairs removed) helps.
3. **Most training data is PopSign (phone selfie camera, signers seated or standing close)** and our eval is LOSO within PopSign; the glasses camera is a different viewpoint (egocentric, signer in front of wearer). Domain shift is unmeasured (M2.2 / `--source glasses`).

## 3. Smallest changes, with hour estimates

Estimates are my own for one engineer who knows the repo, assuming landmark data is on disk; none is measured.

### A. Cut vocabulary to 10-20 classes (1.5 h)
Rule: remove the two named confusions' weaker members, then cap at 20 by the lowest per-class top1 in m1.json.
- Drop **HAPPY** (confused into PLEASE) and **TALK** (confused into WATER). PLEASE and WATER stay: both are useful request words and have PopSign data. Dropping the "victim" keeps the higher-value sign; this is a judgement call, flip it if per_class shows PLEASE/WATER are the worse of each pair.
- That leaves 22 signs. Cut 2+ more to reach <=20, chosen from `m1.json per_class` (lowest top1 first). I cannot name them without that file. The VOCAB.md notes already flag HELLO/BYE and WATER/THANKYOU as likely confusions: check `top_confusions` for those first.
- Prefer PopSign-only classes. Own-recorded HELP, QUESTION, UNDERSTAND, AGAIN depend on recordings that do not exist in this checkout; keep at most the ones actually recorded with >=3 signers.
- Candidate 16-class demo set if the lead wants a default now (unmeasured; check against per_class): HELLO, BYE, YES, NO, PLEASE, THANKYOU, WAIT, FINISH, POTTY, WATER, WHERE, WHY, WHO, BOOK, HOME, HELP. Gives phrases "Hello", "Where is the book?", "Please wait", "Help", "Thank you, bye".
- How: do not edit the frozen VOCAB.md/§0 "24" without a contract change; instead add an optional `SIGNER_VOCAB` (comma list) / `--vocab` filter read by `load_dataset(vocab=...)` (already supported at `data.py:55-57`) and by `eval/run.py`. Update `/health.vocab` from the live classifier. Retrain is free for kNN. Deliver as a flag-first change, then the lead decides whether to freeze VOCAB.md at the smaller set.
- Rejecting with coverage in mind: fewer classes also raises vote share per class, so coverage at the 0.80 gate should rise. By how much is unmeasured; re-run `python eval/run.py --loso --out eval/results/m1b.json` after the cut.

### B. LSTM/GRU on the existing landmarks `.npz` (6-8 h incl. eval; the M2.2 task)
- Input: reuse `vision.features.clip_features(xyz, steps)` -> `(32, 180)` per clip (NaN-safe, presence flags, shoulder-normalised; `features.py:140`). **No new data format**, no extraction rerun: it reads the same `data/popsign/landmarks/<GLOSS>/*.npz` and `data/landmarks/...` via `model.data.load_dataset` (`data.py:55`).
- New file `core/signer_core/model/lstm.py` (owned by data-ml, M2 contract owned paths already include `core/signer_core/model/**`): `LSTMClassifier` with `fit(clips, labels)`, `predict_proba(xyz)`, `predict(xyz, top)`, `classes`, `save/load` (torch `state_dict` + class list + feature stats in one `.pt`). Model: 2-layer bidirectional LSTM (hidden ~128) or 1 layer GRU on `(32, 180)`, mean+max pooled over time, linear head. Augment: the existing `mirror()` (`knn.py:30-34`), small time-warp (resample to 24-40 steps then 32), noise, hand dropout. Loss: cross-entropy + label smoothing. No pretrained weights, so "avoid training large nets" is met (parameters in the low hundreds of thousands; CPU-trainable, unmeasured).
- Confidence: softmax, temperature-scaled on a held-out signer split (as `KNNClassifier.calibrate` does). Rejection: keep `tier_for` thresholds, plus **max-softmax floor** and an "unknown" margin rule (top1 - top2) because a softmax head is overconfident on novel motion, which the kNN's novelty factor handled implicitly. Without this rule the LSTM can break the "reject, do not invent" requirement; this is the main risk of swapping.
- Eval: add the class to `eval/run.py` as `--model lstm` (see C). Compare with the kNN under the same LOSO folds; ship whichever wins on held-out signers (matches the plan, DECISION.md:52). Report top1/top3/selective_acc/coverage per `CONTRACTS §6`.
- Add `torch` (CPU wheel) to `core/pyproject.toml` as an **optional extra** (`lstm`) so the base install and CI stay light; torch needs the Python version the venv uses (mediapipe pins `>=3.11,<3.13`): confirm a CPU wheel exists for 3.12 on each laptop before relying on it.
- Honest expectation: I will not predict accuracy. PopSign paper-level LSTM numbers were on all 250 classes with full-frame landmarks incl. face; ours differ in features, classes and sample count.

### C. Make the classifier interface genuinely swappable (2 h; do before B)
1. `core/signer_core/model/base.py`: `typing.Protocol` `SignClassifier` with `classes: list[str]`, `fit(clips, labels)`, `predict_proba(xyz)->dict`, `predict(xyz, top=3)->list[(gloss, conf)]`, optional `add/remove` (teach), `save(path)/load(path)`. KNNClassifier already satisfies it (`knn.py:47`).
2. `model/registry.py`: `MODELS = {"knn": KNNClassifier, "lstm": LSTMClassifier}`; `build_classifier(name=os.environ.get("SIGNER_MODEL","knn"), ...)` replaces the hard-wired return (`recognizer.py:62`). Make `/health.model` report the real class (`relay/app.py:98`). Cache/load a saved model if present so Start does not refit.
3. `eval/run.py`: replace the name-guessing `RealModel.CANDIDATES` (`run.py:214`) with `--model <registry key>`; keep `baseline` as is. Tests: protocol conformance test per registered model; a fake classifier passed to `Recognizer` (test_model.py has 10 tests today; extend).
This touches `model/**`, `eval/**`, one line in `relay/app.py` (M2 contract lists `relay/**` as owned by the backend task, so coordinate).

### D. Evaluate a pretrained model (1-2 h time-box, optional)
Aim: tick the "evaluate a pretrained model first" box honestly. Spend one bounded hour checking whether PopSign's published LSTM weights (or any ASL isolated-sign landmark model) are downloadable without Kaggle and use the same Holistic index layout. If not reachable, say so in the deck ("no accessible pretrained weights; dataset evaluated"). Risk noted in research: layout mismatch with Tasks-API Holistic (`research/sign-recognition.md:44` caveat). I have not checked availability; unmeasured.

### E. Face and temporal extras (only if A-C done; 3-4 h each, low priority)
- Keep face blendshapes live only: `output_face_blendshapes=True` (`holistic.py:69`) and read brow/mouth features in a new `vision/face.py` for the question flag (PLAN M3.2). Do **not** add to the stored 75-point npz or classifier input until it is shown to help; the 543-point storage was rejected for size (CONTRACTS §5).
- Optional DTW/soft-DTW distance in the kNN to handle speed variation (1 d feature, unmeasured gain).

## 4. Recommended order (total about 10-12 h of the 37 h budget; the first three are the objective's blockers)
1. C interface swap (2 h) so nothing else blocks on kNN.
2. A vocabulary cut to <=20 and re-run LOSO (1.5 h). Cheapest accuracy/coverage gain; no new model risk.
3. B LSTM + eval (6-8 h). Satisfies "PyTorch temporal classifier / LSTM baseline" outright; ship only if it beats kNN on LOSO and keeps the rejection behaviour.
4. D pretrained check (1-2 h, parallelisable) and E only with spare time.
Check results against `eval/results/*.json` only; do not quote this file's estimates as measurements.

## 5. Contract notes for the lead
- Changing 24 -> <=20 signs touches CONTRACTS §0/§5, `/health.vocab:24`, VOCAB.md ("frozen in M0.4"). Use a flag first (A) and record the contract change in STATE.md when the vocabulary is final.
- Adding `torch` to `core/pyproject.toml` is a shared-file change; make it an optional extra.
- No code was changed by this mission.
