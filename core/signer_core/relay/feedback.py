"""Signer-side trust controls on the relay (CONTRACTS §2, M3): Teach-a-sign routes + the hooks they need.

    from .feedback import install; install(app, relay)      # in create_app, before `return app`

Right / Wrong / Not right (veto -> `retract`) and the `stats` readout are `Relay.feedback` (M1). This adds:
- `POST /teach {"gloss","english"}` -> `{"teach_id","reps_needed":5}`: the next 5 signed segments are stored as
  prototypes (no captions while teaching) and the sign is recognised from the next segment on.
- `GET /teach` -> `{"taught":[{"gloss","english","reps"}]}` (the card polls it for progress).
- `DELETE /teach/{gloss}` -> `{"deleted":true}`: files and prototypes gone in one tap.
Teach is a graft behind `SIGNER_FLAGS=teach`; without it the routes answer 404 `teach_off` (the card hides it).
Stop / idle stop cancels a teach in progress, like any other consent reset.
"""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.routing import Mount

from ..language import ENGLISH
from ..model.teach import TeachError, TeachRecognizer, TeachStore


class TeachBody(BaseModel):
    gloss: str
    english: str


def flags(env=None) -> set[str]:
    raw = (os.environ if env is None else env).get("SIGNER_FLAGS", "")
    return {f.strip().lower() for f in raw.split(",") if f.strip()}


def _bad(status: int, error: str) -> JSONResponse:
    return JSONResponse({"error": error}, status_code=status)


def install(app, relay, enabled: bool | None = None, store: TeachStore | None = None) -> TeachStore:
    """Wire Teach into `relay` and add the /teach routes to `app` (ahead of the card's static mount)."""
    enabled = "teach" in flags() if enabled is None else enabled
    base = {row["gloss"] for row in relay.vocab()}
    store = store or TeachStore(Path(relay.data_dir) / "taught", reserved=base)
    relay.teach = store
    english = relay.pipeline.phrases.english
    if english is ENGLISH:  # never grow the module-wide default
        english = relay.pipeline.phrases.english = dict(ENGLISH)

    def on_rep(gloss: str) -> None:
        relay.session.touch()  # teaching is activity: no idle stop mid-teach
        if store.done(gloss):
            english.update(store.english())

    pipeline = relay.pipeline
    plain_set_classifier = pipeline.set_classifier

    def set_classifier(classifier) -> None:
        plain_set_classifier(classifier)
        store.reserved |= set(classifier.labels) - set(store.glosses())  # trained signs are never taught over
        if enabled:
            store.apply(classifier)
            english.update(store.english())
            pipeline.recognizer = TeachRecognizer(classifier, store, pipeline.recognizer.segmenter, on_rep)

    pipeline.set_classifier = set_classifier
    if pipeline.classifier is not None:
        set_classifier(pipeline.classifier)

    plain_stop = relay.stop

    async def stop(by: str) -> dict:
        snap = await plain_stop(by)
        store.cancel()
        return snap

    relay.stop = stop

    plain_vocab = relay.vocab

    def vocab() -> list[dict]:
        rows = plain_vocab()
        if enabled:
            rows += [{"gloss": g, "english": e, "source": "taught"} for g, e in store.english().items()]
        return rows

    relay.vocab = vocab

    router = APIRouter()

    @router.post("/teach")
    async def teach_begin(body: TeachBody):
        if not enabled:
            return _bad(404, "teach_off")
        try:
            out = store.begin(body.gloss, body.english)
        except TeachError as e:
            return _bad(409 if e.code == "gloss_exists" else 422, e.code)
        clf = pipeline.classifier
        if clf is not None:
            clf.remove(store.active["gloss"])  # retaught: old prototypes go
        relay.session.touch()
        return out

    @router.get("/teach")
    async def teach_list():
        if not enabled:
            return _bad(404, "teach_off")
        return {"taught": store.list()}

    @router.delete("/teach/{gloss}")
    async def teach_delete(gloss: str):
        if not enabled:
            return _bad(404, "teach_off")
        if gloss.strip().upper() in store.reserved:
            return _bad(409, "gloss_exists")
        if not store.delete(gloss, pipeline.classifier):
            return _bad(404, "unknown_gloss")
        english.pop(gloss.strip().upper(), None)
        return {"deleted": True}

    app.include_router(router)
    # the card is mounted at "/" and would shadow routes added after it: keep mounts last
    app.router.routes.sort(key=lambda r: isinstance(r, Mount))
    return store
