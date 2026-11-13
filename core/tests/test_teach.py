"""M3.3 Teach-a-sign: POST/GET/DELETE /teach, 5 reps -> kNN prototypes, recognised next, one-tap delete, flag.

Synthetic landmarks only (test_model helpers): the base model knows 4 signs, the 5th pattern is taught live.
"""
import json

import numpy as np
import pytest
from fastapi.testclient import TestClient

from signer_core.model import KNNClassifier
from signer_core.model.teach import TeachError, TeachStore
from signer_core.relay.app import create_app
from signer_core.relay.feedback import flags, install
from test_model import GLOSSES, body, dataset, sign_clip
from test_relay import fake_landmarker, frame_msg, recv_until

NEW = 4  # GLOSSES[4]'s trajectory, taught as a new gloss


@pytest.fixture
def classifier():
    X, y = dataset(8, seed=0)
    keep = [i for i, g in enumerate(y) if g != GLOSSES[NEW]]
    return KNNClassifier().fit([X[i] for i in keep], [y[i] for i in keep])


def teach_client(classifier, tmp_path, enabled=True):
    app = create_app(classifier=classifier, landmarker=fake_landmarker, phrase_gap_ms=1500, card_dir=str(tmp_path))
    store = install(app, app.state.relay, enabled=enabled, store=TeachStore(tmp_path / "taught"))
    return TestClient(app), store


def reps_stream(cls, n, seed=3):
    rng = np.random.default_rng(seed)
    return np.concatenate([np.concatenate([sign_clip(cls, rng, t=30, rest_pad=15), body(30)]) for _ in range(n)]
                          + [body(90)])


def send(ws, frames, seq0=0):
    """Send frames and wait for the core's acks, so everything sent before the last ack has been processed."""
    for i, f in enumerate(frames):
        ws.send_bytes(frame_msg(f, seq0 + i, (seq0 + i) * 33))
    for _ in range((seq0 + len(frames)) // 30 - seq0 // 30):
        assert json.loads(ws.receive_text())["type"] == "ack"
    return seq0 + len(frames)


def test_teach_five_reps_then_recognised_then_deleted(classifier, tmp_path):
    client, store = teach_client(classifier, tmp_path)
    assert client.get("/teach").json() == {"taught": []}
    client.post("/session/start", json={"by": "card"})
    r = client.post("/teach", json={"gloss": "projector", "english": "projector"})
    assert r.status_code == 200 and r.json() == {"teach_id": "t1", "reps_needed": 5}

    with client.websocket_connect("/ws/events") as ev:
        ev.receive_text(), ev.receive_text()
        with client.websocket_connect("/ws/frames") as ws:
            seq = send(ws, reps_stream(NEW, 5))
            assert client.get("/teach").json() == {"taught": [{"gloss": "PROJECTOR", "english": "projector",
                                                               "reps": 5}]}
            assert store.active is None  # teaching ended by itself after rep 5
            assert "PROJECTOR" in classifier.labels
            send(ws, reps_stream(NEW, 1, seed=11), seq)
            cap = recv_until(ev, "caption")
        assert cap["gloss"] == ["PROJECTOR"], cap  # no caption was made from the 5 reps themselves
        assert cap["id"] == "c1" and "projector" in cap["text"].lower()

    files = sorted(p.name for p in (tmp_path / "taught" / "PROJECTOR").iterdir())
    assert files == ["0.npz", "1.npz", "2.npz", "3.npz", "4.npz", "meta.json"]
    with np.load(tmp_path / "taught" / "PROJECTOR" / "0.npz") as d:
        assert d["xyz"].dtype == np.float16 and d["xyz"].shape[1:] == (75, 3) and str(d["source"]) == "taught"
    assert {"gloss": "PROJECTOR", "english": "projector", "source": "taught"} in client.get("/vocab").json()["signs"]

    assert client.delete("/teach/PROJECTOR").json() == {"deleted": True}
    assert "PROJECTOR" not in classifier.labels and not (tmp_path / "taught" / "PROJECTOR").exists()
    assert client.get("/teach").json() == {"taught": []}
    assert client.delete("/teach/PROJECTOR").status_code == 404


def test_teach_rejects_trained_and_bad_glosses(classifier, tmp_path):
    client, _ = teach_client(classifier, tmp_path)
    r = client.post("/teach", json={"gloss": "HELLO", "english": "hi"})
    assert r.status_code == 409 and r.json() == {"error": "gloss_exists"}
    assert client.delete("/teach/HELLO").status_code == 409
    assert "HELLO" in classifier.labels  # a trained sign is never deleted from here
    assert client.post("/teach", json={"gloss": "no spaces", "english": "x"}).json() == {"error": "bad_gloss"}
    assert client.post("/teach", json={"gloss": "LAMP", "english": " "}).json() == {"error": "bad_english"}


def test_stop_cancels_teaching_and_partial_sign_is_not_used(classifier, tmp_path):
    client, store = teach_client(classifier, tmp_path)
    client.post("/session/start", json={"by": "card"})
    client.post("/teach", json={"gloss": "LAMP", "english": "lamp"})
    with client.websocket_connect("/ws/frames") as ws:
        send(ws, reps_stream(NEW, 2))
        client.post("/session/stop", json={"by": "card"})
    assert store.active is None
    assert client.get("/teach").json()["taught"] == [{"gloss": "LAMP", "english": "lamp", "reps": 2}]
    assert "LAMP" not in classifier.labels and "LAMP" not in store.english()


def test_taught_signs_reload_into_a_new_model(classifier, tmp_path):
    store = TeachStore(tmp_path)
    store.begin("LAMP", "lamp")
    rng = np.random.default_rng(0)
    for _ in range(5):
        assert store.capture(sign_clip(NEW, rng)) == "LAMP"
    assert store.capture(sign_clip(NEW, rng)) is None  # done: nothing more is captured
    assert store.apply(classifier) == ["LAMP"] and store.apply(classifier) == []  # added once
    assert classifier.labels.count("LAMP") == 10  # 5 reps + mirrors
    assert classifier.predict(sign_clip(NEW, rng))[0][0] == "LAMP"
    with pytest.raises(TeachError):
        TeachStore(tmp_path, reserved=["LAMP"]).begin("lamp", "lamp")


def test_teach_is_off_without_the_flag(classifier, tmp_path):
    client, _ = teach_client(classifier, tmp_path, enabled=False)
    for r in (client.get("/teach"), client.post("/teach", json={"gloss": "LAMP", "english": "lamp"}),
              client.delete("/teach/LAMP")):
        assert r.status_code == 404 and r.json() == {"error": "teach_off"}
    assert flags({"SIGNER_FLAGS": "llm, Teach"}) == {"llm", "teach"} and flags({}) == set()


def test_create_app_installs_teach_only_with_the_flag(classifier, tmp_path, monkeypatch):
    monkeypatch.setenv("SIGNER_DATA_DIR", str(tmp_path))
    off = TestClient(create_app(classifier=classifier, landmarker=fake_landmarker, card_dir=str(tmp_path)))
    assert off.get("/teach").status_code == 404 and getattr(off.app.state.relay, "teach", None) is None
    monkeypatch.setenv("SIGNER_FLAGS", "teach")
    on = TestClient(create_app(classifier=classifier, landmarker=fake_landmarker, card_dir=str(tmp_path)))
    assert on.get("/teach").json() == {"taught": []}


def test_teach_routes_win_over_the_card_mount(classifier, tmp_path):
    (tmp_path / "index.html").write_text("<h1>card</h1>", encoding="utf-8")
    client, _ = teach_client(classifier, tmp_path)
    assert client.get("/teach").json() == {"taught": []}
    assert "card" in client.get("/").text
    assert json.loads(client.get("/health").text)["status"] == "ok"
