# HF landmark / large-scale ASL datasets (mission m-78e75, 2026-11-14)

All numbers below were read from the HF API (`/api/datasets/<id>?blobs=true`), README files and
one downloaded sample, not guessed. "Verified" is marked where I opened a file myself.

## Headline

1. **There is no usable Hugging Face mirror of the Google ISLR `asl-signs` set (94,477 clips).**
   Searches run on the HF datasets API: `asl-signs`, `asl_signs`, `isolated sign language`, `islr`,
   `gislr`, `sign_to_prediction`, `kaggle asl`, `asl parquet`, `mediapipe holistic`, `asl 250`,
   `asl-islr`, `popsign`, plus paged scans of `asl`, `sign`, `landmarks`, `holistic`. The only repo names that
   match are `cornelismus/asl_signs` and `Keithsel/asl_signs`. I listed both: **they are ASL-alphabet
   JPEG images** (126 files, 18-29 MB), not the Google landmark set. `A-Z-E/aslKaggleSet` is also a
   letters set. A web search found no mirror either. Rejected.
2. **Best substitute: ASL Citizen poses, `SorensenAI/asl-citizen-poses`.** Isolated-sign clips
   with MediaPipe Holistic landmarks already extracted, 21 of our 24 glosses present with 30-76 clips each
   (23 of 24 if we map THANKYOU and POTTY to ASL Citizen's `THANK YOU` and `TOILET`/`BATHROOM`),
   ~100k files. Gaps and licence risk are below.
3. **Second: WLASL** (all 24 glosses, 10-40 videos each, 119 signers). Videos are the usual form, so you
   need extraction; ready-made landmark versions on HF are small or use other layouts.

## Ranked table

Gloss coverage = how many of our 24 glosses appear (exact, case-insensitive, trailing digit variant
suffix stripped) in the label source named in the cell.

| # | id | URL | licence | gated | format | size | clips | signers | our-gloss coverage | leakage risk vs our PopSign set | conversion effort |
|---|----|-----|---------|-------|--------|------|-------|---------|--------------------|---------------------------------|-------------------|
| 1 | `SorensenAI/asl-citizen-poses` | https://huggingface.co/datasets/SorensenAI/asl-citizen-poses | **none declared** (no README; upstream ASL Citizen is non-commercial research licence, so treat as research/prototype only) | no | `.pose` files (pose-format), 576 pts x XYZC per frame, ~30 fps. File name = `<id>-<GLOSS>.pose`; **no train.csv, label = file name** | 77.8 GB for the 99,999 listed files (listing capped at 100k entries; may be more) | ~99,999 listed, 4,485 distinct gloss names (incl. `SEED...` duplicates) | ~52 in the upstream paper, ids anonymised here | 21/24 exact; **23/24** with `THANK YOU` (40), `TOILET` (39) / `BATHROOM` (35). Missing: QUESTION. Per gloss 29-76: HELLO 42, BYE 32, YES 33, NO 29, PLEASE 31, WAIT 32, FINISH 41, WATER 34, WHERE 32, WHY 39, WHO 42, TIME 36, BOOK 35, LISTEN 39, TALK 76, HOME 35, SICK 39, HAPPY 32, HELP 34, UNDERSTAND 32, AGAIN 36 | **Low.** ASL Citizen was recorded by Microsoft/BU/Gallaudet on signers' own webcams, a different pipeline from PopSign. No id overlap possible to check (anonymised). Still, treat as unverified | Medium: parse `.pose`, select by file name, subset 576 -> 75 (mapping below) |
| 2 | `SorensenAI/asl-citizen-poses-anonym` | https://huggingface.co/datasets/SorensenAI/asl-citizen-poses-anonym | none | no | same `.pose`, batches `batch_005...` | 48.5 GB, 62,376 files | 62k | same | not counted; same naming | same | same. Use only if #1 is too big; likely a subset/other split |
| 3 | `SharoonArshad/asl-citizen-processed-200` | https://huggingface.co/datasets/SharoonArshad/asl-citizen-processed-200 | cc-by-nc-sa-4.0 | no | **already 75 pts**: shards `.npy`, resampled to 200 frames, shoulder-centred/shoulder-width-normalised, +velocity (feature dim 450, float16); labels as int ids + `label_to_id.json` | 1.86 GB, 95 files | 10,296 (train 6,090 / val 654 / test 3,552) | ~52 | **only 200 classes: 4/24 exact** (hello, finish, why, understand); `no` absent (only `north`) | low | Low *if* you accept its normalisation, but the 4 glosses are too few. Not useful for us except as a format example |
| 4 | WLASL, many copies (`Voxel51/WLASL`, `Dayeer/WLASL`, `34data/wlasl`, `luciayen/pose-extra-WLASL` ...) | https://huggingface.co/datasets/Voxel51/WLASL | mixed / mostly undeclared (upstream C-UDA, non-commercial) | no | MP4 videos; `luciayen` has `.npy` pose (10 GB, 11,983 files) of unspecified layout | multi-GB | 21,083 instances (from `WLASL_v0.3.json`, which I downloaded and counted) | 119 | **24/24** (THANKYOU as `thank you`, POTTY as `bathroom` 16 / `toilet` 13): hello 13, bye 7, yes 22, no 22, please 15, thank you 14, wait 18, finish 21, water 18, where 15, why 17, who 25, time 19, book 40, listen 11, talk 14, home 16, sick 17, happy 16, help 22, question 10, understand 14, again 16 | Low-medium (web/YouTube videos, many sources; some may be from ASLU, not PopSign) | High (video -> Holistic extraction on the Verda box). Many dead/low-quality videos |
| 5 | `Kibalama/wlasl-upper-arm-pose-landmarks` | https://huggingface.co/datasets/Kibalama/wlasl-upper-arm-pose-landmarks | none | no | parquet, `poses` nested float64 + `label`, MediaPipe Lite **pose only** | 10 MB | 1,000 | n/a | not counted | low | Unusable: pose only, 1,000 rows, no hands |
| 6 | `martinctl/how2sign-asl-landmarks`, `PSewmuthu/How2Sign_Holistic` (MIT), `bdanko/how2sign-landmarks-front-raw-parquet`, `ASL-Live-Video-Translation/how2sign-realigned-mediapipe` | https://huggingface.co/datasets/PSewmuthu/How2Sign_Holistic | cc-by-nc-4.0 (martinctl, ASL-Live), MIT (PSewmuthu, the card's licence field; upstream How2Sign is CC BY-NC 4.0) | no | sentence-level MediaPipe Holistic landmark NPZ/parquet, 12-37 GB | 12 GB / 34 GB / 37 GB / 0.24 GB | ~35k sentences | ~11 | **Continuous sentences, not isolated signs, no gloss labels**; would need word alignment. Not usable for our 24-class classifier | none with PopSign | High |
| 7 | `mage0001/ASLCitizen-3D` | https://huggingface.co/datasets/mage0001/ASLCitizen-3D | none | no | SMPL-X reconstructions in tar | 18.4 GB | n/a | n/a | n/a | low | Wrong representation for us |
| 8 | `Kibalama/ChicagoFSWild-Landmarks` | https://huggingface.co/datasets/Kibalama/ChicagoFSWild-Landmarks | none | no | parquet train/val/test | 414 MB | n/a | n/a | n/a (fingerspelling) | n/a | Fingerspelling only; note for later |

## Google ASL Fingerspelling mirrors (low priority, note only)

No mirror of the Kaggle `asl-fingerspelling` landmark set found. Related repos: `sid220/asl-now-fingerspelling`
(letters, images), `Kibalama/ChicagoFSWild-Landmarks` (landmarks, 414 MB, no licence), `fhswf/wholebody-...-fingerspelling`
(German DGS, not ASL; rejected).

## Egocentric / first-person signing

Nothing useful. `jackji/signiq-egocentric-handpose-sample` (CC BY 4.0) is five 30 s head-mounted GoPro clips of
**manipulation**, not signing (confirmed from its README: "manipulation clips for hand-pose / action-segment
annotation"). No egocentric ASL dataset found on HF. Implication: for the Ray-Ban view, we must record our own
or rely on the frontal view with augmentation (this is the receiver's view of the signer, anyway: the glasses
face the signer, so **frontal third-person data is the correct domain**).

## Top recommendation: ASL Citizen poses (`SorensenAI/asl-citizen-poses`)

Why: only large source where landmarks already exist, front-facing webcam signers, and almost all of our
glosses are present with 29-76 examples each. It is more than our PopSign has per gloss for most classes
(PopSign: ~333 clips/gloss on average, so ASL Citizen adds ~10% per gloss but with ~52 *new* signers,
which is what improves signer-disjoint accuracy).

Risks to state plainly:
- **No licence on the HF repo**; upstream ASL Citizen is released for non-commercial research. Fine for a
  hackathon prototype, not for shipping a commercial product.
- QUESTION is missing; map to nothing (keep PopSign only for it). THANKYOU and POTTY need the alias map below.
- Sign-variant suffixes (`HELLO 1`, `HELLO 2`) are in the file name; strip trailing ` <digit>`.
- Several `.pose` files have an empty hand (verified on my sample, a `HELLO`: right hand 100% NaN in all frames,
  i.e. one-handed sign, expected). Our clip format already uses NaN = missing, so this matches.
- Coordinates are **pixels** (sample min/max -376..1128, header 512x512 but values exceed it, so the header
  width/height is unreliable). Our `features.py` centres on the shoulder midpoint and divides by shoulder
  width, which is scale-invariant for isotropic pixels, so no rescale is needed. Do not divide by the header
  dimensions. Our pipeline divides x and y by width and height separately in image space (a known limit
  in `features.py`); pixels are slightly more correct, but confirm accuracy on a hold-out before mixing.
- Signer overlap with PopSign is not checkable (ids anonymised) but sources differ; low risk.

### Download (do NOT pull all 78 GB; select by file name)

```bash
pip install -U huggingface_hub pose-format
python - <<'PY'
import re
from huggingface_hub import HfApi, hf_hub_download
api = HfApi()
ALIAS = {"THANK YOU":"THANKYOU","TOILET":"POTTY","BATHROOM":"POTTY"}
WANT = set("HELLO BYE YES NO PLEASE WAIT FINISH WATER WHERE WHY WHO TIME BOOK LISTEN TALK HOME SICK HAPPY HELP UNDERSTAND AGAIN".split()) | set(ALIAS)
files = [f for f in api.list_repo_files("SorensenAI/asl-citizen-poses", repo_type="dataset") if f.endswith(".pose")]
sel = []
for f in files:
    g = f.rsplit("/",1)[-1][:-5].split("-",1)[-1]        # '<id>-<GLOSS>.pose'
    g = re.sub(r"\s*\d+$","",g).upper().strip()          # drop variant digit; skip SEED... names
    if g in WANT: sel.append(f)
print(len(sel))                                           # ~800 files, ~0.7 GB
for f in sel: hf_hub_download("SorensenAI/asl-citizen-poses", f, repo_type="dataset", local_dir="data/asl_citizen")
PY
```
(about 800 files and < 1 GB; I did not download these, only two sample files.)
Equivalent CLI for one batch: `huggingface-cli download SorensenAI/asl-citizen-poses --repo-type dataset --include "poses_anonymized_batches/batch_001/*" --local-dir data/asl_citizen`.

### Sample file opened (DoD 3)

`poses_anonymized_batches/batch_001/0022932153577568393-HELLO.pose`, 862,687 bytes, read with
`pose_format.Pose.read`:

- `body.data.shape == (92, 1, 576, 3)` = frames x people x points x (x, y, z); `body.confidence` shape (92, 1, 576), range 0-1; fps 29.97.
- Header components (name, points, format): `POSE_LANDMARKS` 33 XYZC; `FACE_LANDMARKS` 468 XYZC;
  `LEFT_HAND_LANDMARKS` 21 XYZC; `RIGHT_HAND_LANDMARKS` 21 XYZC; `POSE_WORLD_LANDMARKS` 33 XYZC.
  (33 + 468 + 21 + 21 + 33 = 576.) Header dimensions 512 x 512 x 0.
- Missing landmarks are masked (NaN after `.filled(nan)`).

This is not Google's parquet (`frame, row_id, type, landmark_index, x, y, z`); that format was not
available, so I could not open one. The Kaggle layout (543 = 468 face + 33 pose + 21 + 21) is known from the
public description only.

### 576 / 543 -> 75 mapping

Our layout (`core/signer_core/vision/clip.py`, `features.py`): index 0-32 pose, 33-53 left hand, 54-74 right hand,
x/y/z, NaN = missing.

**ASL Citizen `.pose` (576 points, component order above):**

| ours | source rows in the 576 axis |
|------|------------------------------|
| 0..32 pose | 0..32 (`POSE_LANDMARKS`) |
| face | 33..500, **drop** |
| 33..53 left hand | 501..521 (`LEFT_HAND_LANDMARKS`) |
| 54..74 right hand | 522..542 (`RIGHT_HAND_LANDMARKS`) |
| world pose | 543..575, **drop** |

```python
import numpy as np
from pose_format import Pose
p = Pose.read(open(path, "rb").read())
d = np.asarray(p.body.data.filled(np.nan))[:, 0, :, :3]       # (T, 576, 3)
xyz = np.concatenate([d[:, 0:33], d[:, 501:522], d[:, 522:543]], axis=1)   # (T, 75, 3)
# prefer reading offsets from the header, not hard-coding:
# off=0; for c in p.header.components: print(c.name, off, off+len(c.points)); off+=len(c.points)
```
Check on a first file: `len` of each header component must be 33/468/21/21/33 or the offsets are wrong.
Also confirm left/right match our convention (MediaPipe Holistic `left_hand` = subject's left in the
un-mirrored image); if our PopSign pipeline mirrors the webcam, apply the same flip (swap 33..53 and 54..74,
negate x about the shoulder midpoint) or the model will see mirrored data.

**Google ISLR parquet (543 pts, if ever obtained):** per frame, rows by `type` and `landmark_index`:
`pose` 0..32 -> ours 0..32; `left_hand` 0..20 -> 33..53; `right_hand` 0..20 -> 54..74; drop `face` (468).
Equivalently in the stacked order [face 0-467, left_hand 468-488, pose 489-521, right_hand 522-542]:
ours = concat(rows 489:522, rows 468:489, rows 522:543). Pivot long-form rows to (T, 543, 3) via `frame` and `landmark_index`.
Its coordinates are normalised 0-1 image coords like ours.

## Rejected

| id | reason |
|----|--------|
| `cornelismus/asl_signs`, `Keithsel/asl_signs` | ASL alphabet JPEGs, not Google ISLR; 18-29 MB |
| `A-Z-E/aslKaggleSet` | alphabet letters |
| `sign/popsign-images` | CC BY 4.0, 90.8 GB frame images, **is** PopSign (our own source; same signers, leakage) |
| `danielelvs/multilingual-islr-mediapipe` | MIT, 14 GB CSV landmarks, but Brazilian/Indonesian/Kazakh-Russian sign languages, not ASL |
| `ASLP-lab/MS-Bench` | name search for MS-ASL found no landmark set; this repo was not opened and looks unrelated (speech bench) |
| `khuranaradhika/asl-realtime-keypoints` | gated (manual), tiny |
| `WenhaoWang/ASL` | 135 GB image-matching set, NC, unrelated |
| `fhswf/wholebody-...-fingerspelling`, `kirandevraj/ISL-Fingerspelling`, `LightScrn/Indian-...` | DGS / Indian sign language |
| How2Sign landmark repos | sentence-level, no gloss labels (see table row 6) |
| `jackji/signiq-egocentric-handpose-sample` | egocentric but manipulation, not signing |

## Checks against the DoD

1. File exists, >= 6 candidates checked: yes (12+ repos opened: both asl_signs repos, ASL Citizen x4, WLASL, How2Sign x4, fingerspelling, egocentric, MS-Bench, multilingual-ISLR).
2. Gloss coverage counted from labels for the top pick: yes, from the repo's file names (no `train.csv` exists); 21/24 exact, 23/24 aliased. WLASL counted from `WLASL_v0.3.json` (24/24).
3. One sample parquet opened: **not parquet**. The top pick ships `.pose`, not parquet, so I opened one `.pose` and listed its columns/components above. No parquet of the Google set exists on HF.
