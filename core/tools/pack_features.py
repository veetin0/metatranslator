"""Pack PopSign landmark clips into one small features file the crew can train on.

The raw clips (data/popsign/landmarks, ~65 MB) are too big for the team server, so they stay on the lead's Mac
(gitignored). This writes data/popsign/features.npz with the same features the model uses at run time:

    X       float16 (N, RESAMPLE_STEPS, F)   signer_core.vision.features.clip_features(xyz)
    gloss   str (N,)
    signer  str (N,)
    clip_id str (N,)

    PYTHONPATH=core core/.venv/bin/python core/tools/pack_features.py
"""
from pathlib import Path

import numpy as np

from signer_core.vision.features import clip_features

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "data" / "popsign" / "landmarks"
OUT = ROOT / "data" / "popsign" / "features.npz"


def main() -> None:
    X, gloss, signer, clip_id = [], [], [], []
    for f in sorted(SRC.glob("*/*.npz")):
        d = np.load(f)
        X.append(clip_features(d["xyz"].astype(np.float32)).astype(np.float16))
        gloss.append(str(d["gloss"]))
        signer.append(str(d["signer"]))
        clip_id.append(f.stem)
    np.savez_compressed(OUT, X=np.stack(X), gloss=np.array(gloss), signer=np.array(signer), clip_id=np.array(clip_id))
    print(f"packed {len(X)} clips {X[0].shape} -> {OUT} ({OUT.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
