"""Load landmark clips for prototypes and eval (CONTRACTS §5 paths)."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from ..vision.clip import load_clip

# source -> glob relative to the data dir
SOURCE_GLOBS = {
    "own": "landmarks/*/*/*.npz",
    "popsign": "popsign/landmarks/*/*.npz",
    "glasses": "glasses/*/*/*.npz",
}


@dataclass
class Dataset:
    xyz: list = field(default_factory=list)
    gloss: list = field(default_factory=list)
    signer: list = field(default_factory=list)
    source: list = field(default_factory=list)
    path: list = field(default_factory=list)

    def __len__(self) -> int:
        return len(self.xyz)

    def subset(self, idx) -> "Dataset":
        return Dataset(*([getattr(self, f)[i] for i in idx] for f in ("xyz", "gloss", "signer", "source", "path")))


def read_vocab(path="data/VOCAB.md") -> list[str]:
    """Glosses from the VOCAB.md table (24 signs + REST), in file order."""
    out = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        m = re.match(r"^\| ([A-Z][A-Z0-9_-]*) \|.*\| (popsign|own) \|", line)
        if m:
            out.append(m.group(1))
    return out


def clip_paths(data_dir="data", sources=("own", "popsign")) -> list[tuple[Path, str]]:
    data_dir = Path(data_dir)
    out = []
    for src in sources:
        if src not in SOURCE_GLOBS:
            raise ValueError(f"unknown source {src!r}; expected one of {sorted(SOURCE_GLOBS)}")
        out += [(p, src) for p in sorted(data_dir.glob(SOURCE_GLOBS[src]))]
    return out


def load_dataset(data_dir="data", sources=("own", "popsign"), vocab=None, exclude_signers=()) -> Dataset:
    """Every readable clip of the given sources; `vocab` (list of glosses) filters labels; bad files are skipped."""
    keep = set(vocab) if vocab else None
    skip = {str(s) for s in exclude_signers}
    ds = Dataset()
    for path, src in clip_paths(data_dir, sources):
        try:
            c = load_clip(path)
        except Exception:
            continue
        g, s = str(c["gloss"]), str(c["signer"])
        if (keep is not None and g not in keep) or s in skip:
            continue
        ds.xyz.append(np.asarray(c["xyz"], dtype=np.float32))
        ds.gloss.append(g)
        ds.signer.append(s)
        ds.source.append(src)
        ds.path.append(str(path))
    return ds
