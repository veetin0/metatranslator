"""Teach-a-sign (CONTRACTS §2, M3): the next `reps_needed` signed segments become kNN prototypes of a new gloss.

    store = TeachStore("data/taught")       # one folder per gloss: <GLOSS>/meta.json + <GLOSS>/<n>.npz
    store.begin("PROJECTOR", "projector")   # {"teach_id": "t1", "reps_needed": 5}
    store.capture(xyz)                      # while teaching: saves the rep, returns the gloss (None if idle)
    store.apply(classifier)                 # every finished taught sign -> classifier.add(...)
    store.delete("PROJECTOR")               # files gone, prototypes removed from the classifier

Taught clips are landmarks only (CONTRACTS §5 keys, source "taught"), never video, and stay on this machine
(data/taught/ is gitignored). A sign is used for recognition only once all reps are in; one tap deletes it.
"""
from __future__ import annotations

import json
import re
import shutil
import threading
from pathlib import Path

import numpy as np

from .recognizer import Recognizer

REPS_NEEDED = 5
GLOSS_RE = re.compile(r"^[A-Z][A-Z0-9_-]{0,23}$")


class TeachError(ValueError):
    """Bad teach request; `code` is the CONTRACTS error string."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class TeachStore:
    def __init__(self, root, reps_needed: int = REPS_NEEDED, reserved=()):
        self.root = Path(root)
        self.reps_needed = reps_needed
        self.reserved = {str(g).upper() for g in reserved}  # base vocabulary: never overwritten or deleted here
        self._lock = threading.Lock()
        self._n = 0
        self.active: dict | None = None  # {"teach_id", "gloss", "english"}

    # -- files -------------------------------------------------------------------------------------------
    def _dir(self, gloss: str) -> Path:
        return self.root / gloss

    def _reps(self, gloss: str) -> list[Path]:
        return sorted(self._dir(gloss).glob("*.npz"), key=lambda p: int(p.stem))

    def _meta(self, gloss: str) -> dict:
        try:
            return json.loads((self._dir(gloss) / "meta.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {"gloss": gloss, "english": gloss.lower()}

    def glosses(self) -> list[str]:
        if not self.root.is_dir():
            return []
        return sorted(p.name for p in self.root.iterdir() if p.is_dir() and GLOSS_RE.match(p.name))

    # -- API ---------------------------------------------------------------------------------------------
    def list(self) -> list[dict]:
        """GET /teach rows, including a sign still being taught (reps < reps_needed)."""
        return [{"gloss": g, "english": self._meta(g).get("english", g.lower()), "reps": len(self._reps(g))}
                for g in self.glosses()]

    def done(self, gloss: str) -> bool:
        return len(self._reps(gloss)) >= self.reps_needed

    def english(self) -> dict[str, str]:
        """Gloss -> English of finished taught signs (template text)."""
        return {g: self._meta(g).get("english", g.lower()) for g in self.glosses() if self.done(g)}

    def begin(self, gloss: str, english: str) -> dict:
        gloss = str(gloss).strip().upper()
        english = " ".join(str(english).split())
        if not GLOSS_RE.match(gloss):
            raise TeachError("bad_gloss")
        if not english or len(english) > 40:
            raise TeachError("bad_english")
        if gloss in self.reserved:
            raise TeachError("gloss_exists")
        with self._lock:
            d = self._dir(gloss)
            if d.exists():  # re-teaching starts over
                shutil.rmtree(d)
            d.mkdir(parents=True)
            (d / "meta.json").write_text(json.dumps({"gloss": gloss, "english": english}), encoding="utf-8")
            self._n += 1
            self.active = {"teach_id": f"t{self._n}", "gloss": gloss, "english": english}
            return {"teach_id": self.active["teach_id"], "reps_needed": self.reps_needed}

    def capture(self, xyz) -> str | None:
        """Store one rep of the sign being taught; returns its gloss, or None when nothing is being taught.

        Teaching ends by itself after the last rep."""
        with self._lock:
            if self.active is None:
                return None
            gloss = self.active["gloss"]
            d = self._dir(gloss)
            d.mkdir(parents=True, exist_ok=True)
            n = len(self._reps(gloss))
            xyz = np.asarray(xyz, dtype=np.float32)
            np.savez_compressed(d / f"{n}.npz", xyz=xyz.astype(np.float16), gloss=np.array(gloss),
                                signer=np.array("taught"), source=np.array("taught"),
                                t_ms=np.zeros(len(xyz), np.int64), fps=np.float32(0))
            if n + 1 >= self.reps_needed:
                self.active = None
            return gloss

    def cancel(self) -> None:
        """Stop teaching (consent withdrawn); the partial sign stays listed so it can be deleted or retaught."""
        with self._lock:
            self.active = None

    def delete(self, gloss: str, classifier=None) -> bool:
        gloss = str(gloss).strip().upper()
        if gloss in self.reserved or not GLOSS_RE.match(gloss):
            return False
        with self._lock:
            d = self._dir(gloss)
            existed = d.is_dir()
            if existed:
                shutil.rmtree(d)
            if self.active and self.active["gloss"] == gloss:
                self.active = None
        if classifier is not None:
            existed = classifier.remove(gloss) > 0 or existed
        return existed

    def clips(self, gloss: str) -> list[np.ndarray]:
        return [np.load(p)["xyz"].astype(np.float32) for p in self._reps(gloss)]

    def apply(self, classifier) -> list[str]:
        """Add every finished taught sign to the classifier (once each); returns the glosses added."""
        have = set(classifier.labels)
        added = []
        for g in self.glosses():
            if g in have or g in self.reserved or not self.done(g):
                continue
            for xyz in self.clips(g)[: self.reps_needed]:
                classifier.add(xyz, g)
            added.append(g)
        return added


class TeachRecognizer(Recognizer):
    """Recognizer that, while a sign is being taught, stores each segment as a rep instead of classifying it.

    `on_rep(gloss)` runs after each stored rep (idle timer, progress); the finished sign is added to the
    classifier right after its last rep, so it is recognised from the next segment on."""

    def __init__(self, classifier, store: TeachStore, segmenter=None, on_rep=None):
        super().__init__(classifier, segmenter)
        self.store = store
        self.on_rep = on_rep

    def _on_segment(self, seg):
        if seg is not None and self.store.active is not None:
            gloss = self.store.capture(seg.xyz)
            if gloss is not None:
                if self.store.done(gloss):
                    self.store.apply(self.classifier)
                if self.on_rep:
                    self.on_rep(gloss)
                return None
        return super()._on_segment(seg)
