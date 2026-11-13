# PopSign ASL v1.0: how we get the vocabulary signs

Prior data for the kNN/GRU classifier (CONTRACTS.md §5). Source: PopSign ASL v1.0, Georgia Tech / Deaf Professional
Arts Network, 200,686 videos, 250 signs, 47 signers, Google Pixel 4a selfie video. We use only the `popsign` rows of
`data/VOCAB.md` (20 signs) and keep only extracted landmarks; the videos are deleted after extraction.

## Layout of the download (checked 2026-11-13)

- Anonymous, no login or form. HTTP `Range` is supported (`Accept-Ranges: bytes`, `206`).
- The dataset page https://signdata.cc.gatech.edu/view/datasets/popsign_v1_0/ links to per-sign pages
  `/view/datasets/popsign_v1_0/{game,non-game}/<sign>/index.html`. Their "Download" buttons point to
  **one plain (uncompressed) tar per sign and split**:
  `https://signdata.cc.gatech.edu/data/popsign_v1_0/{game,non-game}/{train,val,test}/<sign>.tar`
  (sizes e.g. `thankyou`: train 3.2 GB, val 0.84 GB, test 0.62 GB). There is no per-clip URL and no single big archive.
- `game` = videos that show exactly the target sign (165,198 clips). `non-game` = PopSign's "variant" bucket (other
  ways of signing the word). We only use `game`.
- Members: `<sign>/<participant>-<sign>-<YYYY_MM_DD_HH_MM_SS.mmm>-<take>.mp4`, e.g.
  `hello/4a.8018-hello-2023_01_11_14_40_31.356-0.mp4`. The numeric part of `<participant>` is the signer id (47 distinct,
  `6001` ... `8902`). Clips: 1944x2592 h264, ~30 fps, ~2 s, median 4.8 MB (0.6 to 41 MB).
- **The splits are signer-disjoint**: train 31 signers, val 8, test 8, no overlap (checked on all 20 vocabulary signs).
  So `split` in the manifest can serve as a held-out-signer split for the M1 LOSO/eval protocol.
- The 250 sign names are in the page list; the vocabulary rows use PopSign's exact spelling (`thankyou`, `potty`).
- Not every sign has all clips: `listen` has 396 (28 signers), `why` 452, `water` 636, others 690 to 880.
- Intended use per PopSign's data card: isolated sign recognition. They list continuous recognition and
  sign-to-English translation as unsuitable. Our pipeline classifies isolated signs and builds the English
  sentence from a gloss sequence with a template or LLM; say this honestly in the deck.

## Because the tars are plain, we never download a whole tar

`--refresh-manifest` walks each tar's headers with 512-byte Range requests and records each member's byte offset and
size. Downloading a clip is then one Range request for exactly its bytes (resumable). ~45 MB per 10 clips instead of
a 3 GB tar. A refresh makes ~16,000 small requests (about 5 minutes with 16 connections); the walk is only needed
when the vocabulary changes.

## Files

| Path | What | In git |
|---|---|---|
| `manifest.json` | per vocabulary sign: gloss, sign page URL, the 3 tar URLs + sizes, fetched date, and every clip (`member`, `split`, `signer`, `offset`, `bytes`); 15,655 clips, 2.3 MB, one clip per line | yes |
| `raw/<popsign_name>/*.mp4` | downloaded videos | **no** (`data/popsign/raw/` and `*.mp4` are gitignored; delete after extraction) |
| `landmarks/<GLOSS>/<clip_id>.npz` | extracted landmarks, CONTRACTS.md §5 (written by `extract_landmarks.py`) | yes |

## How to run (from anywhere; paths resolve from the repo root; Python >= 3.10, stdlib only)

```bash
# plan only: reads data/VOCAB.md + manifest.json, no network. Exits 1 if a popsign row has no manifest entry.
python core/tools/get_popsign.py --vocab data/VOCAB.md --dry-run

# download 100 clips per sign, 4 connections (about 12.6 GB for all 20 signs; 36 GB free is enough)
python core/tools/get_popsign.py

# smaller or split across laptops
python core/tools/get_popsign.py --per-sign 40
python core/tools/get_popsign.py --signs HELLO,thankyou --per-sign 5
python core/tools/get_popsign.py --shard 0/3      # laptop A: 0/3, laptop B: 1/3, laptop C: 2/3 (0-based)

# only when VOCAB.md changes: rebuild the manifest (network, ~5 min)
python core/tools/get_popsign.py --refresh-manifest

# offline self checks (tar walker, round-robin picker, vocab parser, dry-run with sockets disabled)
python core/tools/get_popsign.py --selftest
```

- `--per-sign N` picks N clips per sign **round-robin across signer ids** (one clip per signer, then a second from each,
  ...), so the default 100 covers all 47 signers about twice, spread over train, val and test.
- Re-running skips finished files, resumes `.part` files with a Range header, and checks the `ftyp` mp4 marker of
  every finished clip (it fails loudly if the manifest offsets are stale).
- `--shard i/n` splits the sorted plan by index modulo n, so the shards are disjoint and cover everything.
- Disk: 20 signs x 100 clips is about 12.6 GB of video (measured from the manifest, `--dry-run` prints it). Measured
  here: about 3 MB/s over 4 connections (43 MB for 5 clips in 13 s); more `--workers` helps.

## Credit (CC BY 4.0)

> PopSign ASL v1.0, Georgia Institute of Technology and the Deaf Professional Arts Network (Thad Starner, Rohit
> Sridhar, Matthew So, Gururaj Deshpande et al.), https://signdata.cc.gatech.edu, licensed under CC BY 4.0
> (https://creativecommons.org/licenses/by/4.0/). We downloaded a subset of the videos, extracted pose and hand
> landmarks from them, and did not redistribute the videos.

The participants consented to public release of the data, including identifiable video. We do not commit or publish
the videos; the landmark files carry the participant's numeric id only.
