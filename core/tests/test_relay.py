"""M1.2 relay tests: consent gate, WS frames -> caption events, feedback/reply, idle stop, template English, card.

No camera, glasses, network or mediapipe: frames carry raw float32 landmarks in place of the JPEG, decoded by a
fake landmarker, and the classifier is fitted on the synthetic clips from test_model.
"""
import json

import numpy as np
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from signer_core.contracts import NONE_TEXT, pack_frame, tier_for
from signer_core.language import to_english
from signer_core.model import KNNClassifier, Prediction
from signer_core.relay.app import app as default_app
from signer_core.relay.app import create_app
from signer_core.relay.pipeline import PhraseBuilder
from signer_core.relay.session import SessionManager
from test_model import GLOSSES, body, dataset, sign_clip


def fake_landmarker(payload: bytes, header: dict):
    return np.frombuffer(payload, np.float32).reshape(75, 3)


def frame_msg(f75, seq, ts_ms):
    header = {"seq": seq, "ts_ms": ts_ms, "w": 504, "h": 896, "source": "mock", "rot": 0}
    return pack_frame(header, np.asarray(f75, np.float32).tobytes())


@pytest.fixture(scope="module")
def classifier():
    X, y = dataset(8, seed=0)
    return KNNClassifier().fit(X, y)


def make_client(classifier, **kw):
    return TestClient(create_app(classifier=classifier, landmarker=fake_landmarker, phrase_gap_ms=1500, **kw))


def signing_stream(classes, seed=7):
    """Signs separated by ~1 s of rest (one phrase), then 3 s of rest so the phrase closes."""
    rng = np.random.default_rng(seed)
    clips = [sign_clip(c, rng, t=30, rest_pad=15) for c in classes] + [body(90)]
    return np.concatenate(clips)


def recv_until(ws, kind, limit=50):
    for _ in range(limit):
        ev = json.loads(ws.receive_text())
        if ev["type"] == kind:
            return ev
    raise AssertionError(f"no {kind} event")


def test_health_ok_on_default_app():
    r = TestClient(default_app).get("/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"
    assert r.json()["vocab"] == 24 and r.json()["session"] == "off"


def test_consent_frames_refused_while_off(classifier):
    client = make_client(classifier)
    with client.websocket_connect("/ws/frames") as ws:
        with pytest.raises(WebSocketDisconnect) as e:
            ws.receive_text()
    assert e.value.code == 4403


def test_consent_frames_accepted_after_start_and_closed_on_stop(classifier):
    client = make_client(classifier)
    s = client.post("/session/start", json={"by": "card"}).json()
    assert s["state"] == "on" and s["session_id"] == "s1" and s["by"] == "card"
    with client.websocket_connect("/ws/frames") as ws:
        for i in range(30):
            ws.send_bytes(frame_msg(body(1)[0], i, i * 33))
        assert json.loads(ws.receive_text()) == {"type": "ack", "seq": 29}
        assert client.post("/session/stop", json={"by": "card"}).json()["state"] == "off"
        with pytest.raises(WebSocketDisconnect) as e:
            ws.receive_text()
    assert e.value.code == 4403
    with client.websocket_connect("/ws/frames") as ws:  # consent reset: a new Start is needed
        with pytest.raises(WebSocketDisconnect) as e:
            ws.receive_text()
    assert e.value.code == 4403
    assert client.post("/session/start", json={"by": "app"}).json()["session_id"] == "s2"


def test_consent_rejects_unknown_stop_reason(classifier):
    client = make_client(classifier)
    assert client.post("/session/stop", json={"by": "nobody"}).status_code == 422
    assert client.get("/session").json()["state"] == "off"


def test_frames_become_partial_and_caption_events(classifier):
    client = make_client(classifier)
    client.post("/session/start", json={"by": "card"})
    with client.websocket_connect("/ws/events") as ev:
        assert json.loads(ev.receive_text())["state"] == "on"
        assert json.loads(ev.receive_text()) == {"type": "stats", "confirmed": 0, "total": 0}
        ev.send_text(json.dumps({"type": "hello", "client": "hud"}))
        with client.websocket_connect("/ws/frames") as ws:
            for i, f in enumerate(signing_stream([4, 3])):  # WHERE, BOOK
                ws.send_bytes(frame_msg(f, i, i * 33))
            cap = recv_until(ev, "caption")
        assert cap["gloss"] == ["WHERE", "BOOK"] and cap["id"] == "c1" and cap["mode"] == "template"
        assert cap["text"] and cap["tier"] == tier_for(cap["confidence"])
        assert cap["speak"] == (cap["tier"] == "confirmed")
        for alt in cap["alternatives"]:
            assert set(alt) == {"text", "gloss", "confidence"} and len(alt["gloss"]) == 2

        r = client.post("/feedback", json={"caption_id": "c1", "verdict": "veto"})
        assert r.json() == {"confirmed": 0, "total": 1}
        assert recv_until(ev, "retract") == {"type": "retract", "id": "c1"}
        assert recv_until(ev, "stats") == {"type": "stats", "confirmed": 0, "total": 1}
        ev.send_text(json.dumps({"type": "feedback", "caption_id": "c1", "verdict": "right"}))
        assert recv_until(ev, "stats") == {"type": "stats", "confirmed": 1, "total": 2}

        assert client.post("/reply", json={"text": "Sure, page 12", "source": "stt"}).json() == {"ok": True}
        rep = recv_until(ev, "reply")
        assert rep["text"] == "Sure, page 12" and rep["source"] == "stt"
    assert client.post("/feedback", json={"caption_id": "nope", "verdict": "right"}).status_code == 404


def test_stale_wall_clock_frames_are_dropped(classifier):
    client = make_client(classifier)
    relay = client.app.state.relay
    client.post("/session/start", json={"by": "card"})
    old = 1_700_000_000_000  # 2023: far older than 300 ms
    with client.websocket_connect("/ws/frames") as ws:
        for i in range(30):
            ws.send_bytes(frame_msg(body(1)[0], i, old + i))
        ws.receive_text()  # ack: all 30 were read
    assert relay.pipeline.frames == 0 and relay.link == "slow"


def test_idle_stop_resets_consent(classifier):
    t = [0.0]
    client = make_client(classifier, idle_stop_s=120, clock=lambda: t[0])
    relay = client.app.state.relay
    client.post("/session/start", json={"by": "card"})
    t[0] = 119.0
    assert not relay.session.idle_expired()
    with client.websocket_connect("/ws/events") as ev:
        ev.receive_text(), ev.receive_text()
        t[0] = 121.0
        with client.websocket_connect("/ws/frames") as ws:
            ws.send_bytes(frame_msg(body(1)[0], 0, 0))
            with pytest.raises(WebSocketDisconnect) as e:
                ws.receive_text()
        assert e.value.code == 4403
        assert recv_until(ev, "state")["state"] == "off"
    s = relay.session.snapshot()
    assert s["state"] == "off" and s["by"] == "idle"


def test_session_manager_double_start_keeps_session():
    sm = SessionManager(idle_stop_s=0)
    a, b = sm.start("card"), sm.start("card")
    assert a["session_id"] == b["session_id"] == "s1" and not sm.idle_expired()
    assert sm.stop("device")["by"] == "device" and sm.start()["session_id"] == "s2"


def pred(gloss, conf, top=()):
    return Prediction(gloss, conf, tier_for(conf), [(gloss, conf), *top], 0, 500)


def test_phrase_tiers_alternatives_and_none():
    pb = PhraseBuilder()
    c = pb.caption([pred("WHERE", 0.95), pred("BOOK", 0.64, [("WATER", 0.41), ("HOME", 0.2)])], "c2")
    assert c["text"] == "Where is the book?" and c["tier"] == "unsure" and c["question"] and not c["speak"]
    assert c["alternatives"] == []  # confidence gate: a 41% runner-up is not offered
    c = pb.caption([pred("WHERE", 0.95), pred("BOOK", 0.64, [("WATER", 0.50), ("HOME", 0.2)])], "c2b")
    assert c["alternatives"] == [{"text": "Where is the water?", "gloss": ["WHERE", "WATER"], "confidence": 0.5}]
    c = pb.caption([pred("HAPPY", 0.90), pred("WATER", 0.60)], "c2c")  # nonsense pair: keep the stronger sign only
    assert c["gloss"] == ["HAPPY"] and c["dropped"] == ["WATER"] and c["tier"] == "unsure" and not c["speak"]
    c = pb.caption([pred("HAPPY", 0.95), pred("WATER", 0.92)], "c2e")  # model sure of both: shown as signed
    assert c["gloss"] == ["HAPPY", "WATER"] and c["dropped"] == [] and c["tier"] == "confirmed" and c["speak"]
    c = pb.caption([pred("HAPPY", 0.90), pred("WATER", 0.40)], "c2f")  # under 50%: never part of the translation
    assert c["gloss"] == ["HAPPY"]
    c = pb.caption([pred("WATER", 0.90), pred("PLEASE", 0.85)], "c2d")  # sensible pair stays whole
    assert c["gloss"] == ["WATER", "PLEASE"] and c["dropped"] == [] and c["speak"]
    c = pb.caption([pred("HELLO", 0.9), pred("QUESTION", 0.86)], "c1")
    assert c["text"] == "Hello, can I ask a question?" and c["tier"] == "confirmed" and c["speak"]
    c = pb.caption([pred("BOOK", 0.31)], "c3")
    assert c["text"] == NONE_TEXT and c["gloss"] == [] and c["tier"] == "none" and not c["speak"]
    c = pb.caption([pred("HELP", 0.9), pred("BOOK", 0.2)], "c4")  # a 'none' sign is left out of the phrase
    assert c["gloss"] == ["HELP"] and c["text"] == "I need help."
    assert pb.add(pred("YES", 0.9)) is None and pb.tick(500 + 1199) is None and pb.tick(500 + 1200)["text"] == "Yes."


class FakeHaiku:
    def __init__(self, reply):
        self.reply, self.prompts = reply, []

    def complete(self, prompt):
        self.prompts.append(prompt)
        return self.reply


def test_caption_uses_fluent_mode_and_falls_back_on_rejection():
    from signer_core.language import FluentTranslator

    llm = FakeHaiku("Hi, may I ask a question?")
    pb = PhraseBuilder(translator=FluentTranslator(client=llm, env={"SIGNER_LLM": "haiku"}))
    c = pb.caption([pred("HELLO", 0.9), pred("QUESTION", 0.64)], "c1")
    assert c["mode"] == "llm" and c["text"] == "Hi, may I ask a question?" and c["question"]
    assert llm.prompts == ["Glosses: HELLO QUESTION(unsure)\nIt is a question."]  # gloss text only
    llm.reply = "Hello, can I ask the doctor a question?"  # adds a content word: rejected
    c = pb.caption([pred("HELLO", 0.9), pred("QUESTION", 0.9)], "c2")
    assert c["mode"] == "template" and c["text"] == "Hello, can I ask a question?"
    assert PhraseBuilder().caption([pred("YES", 0.9)], "c3")["mode"] == "template"  # off by default


@pytest.mark.parametrize("gloss,text,question", [
    (["HELLO", "QUESTION"], "Hello, can I ask a question?", True),
    (["WHERE", "BOOK"], "Where is the book?", True),
    (["BOOK", "WHERE"], "Where is the book?", True),
    (["WHERE", "POTTY"], "Where is the bathroom?", True),
    (["PLEASE", "WAIT"], "Please wait.", False),
    (["THANKYOU", "BYE"], "Thank you, bye!", False),
    (["HELLO", "HELP"], "Hello, I need help.", False),
    (["HELLO", "WHERE", "WATER"], "Hello, where is the water?", True),
    (["TIME"], "What time is it?", True),
    (["WHY"], "Why?", True),
    (["TALK", "LISTEN", "PLEASE"], "Talk listen, please.", False),
    (["REST"], "", False),
])
def test_template_english(gloss, text, question):
    assert to_english(gloss) == (text, question)


def test_card_served_at_root(tmp_path, classifier):
    r = make_client(classifier, card_dir=str(tmp_path / "missing")).get("/")
    assert r.status_code == 200 and "Start" in r.text  # relay fallback consent page
    (tmp_path / "index.html").write_text("<button>Start</button><!-- the card -->")
    r = make_client(classifier, card_dir=str(tmp_path)).get("/")
    assert r.status_code == 200 and "the card" in r.text
    assert TestClient(default_app).get("/").status_code == 200


def test_app_state_is_passed_on_to_the_card_not_the_session(classifier):
    client = make_client(classifier)
    with client.websocket_connect("/ws/events") as app_ws, client.websocket_connect("/ws/events") as card:
        app_ws.receive_text(), app_ws.receive_text(), card.receive_text(), card.receive_text()
        app_ws.send_text(json.dumps({"type": "state", "state": "glasses_off", "link": "ok", "ts": 1, "from": "app"}))
        ev = recv_until(card, "state")
        assert ev["state"] == "glasses_off" and ev["from"] == "app"
        app_ws.send_text(json.dumps({"type": "state", "state": "off", "from": "app"}))  # not an app state: ignored
        app_ws.send_text(json.dumps({"type": "state", "state": "on", "from": "app"}))
        assert recv_until(card, "state")["state"] == "on"
    assert client.get("/session").json()["state"] == "off"  # consent is only Start/Stop


def test_vocab_lists_signs():
    signs = TestClient(default_app).get("/vocab").json()["signs"]
    assert len(signs) == 24 and {"gloss": "POTTY", "english": "bathroom", "source": "popsign"} in signs
    assert GLOSSES[0] in {s["gloss"] for s in signs}
