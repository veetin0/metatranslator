"""Template mode and the face question flag (vision/face.py)."""
from types import SimpleNamespace

from signer_core.language import apply_question, to_english
from signer_core.vision.face import QuestionDetector, blendshapes_from_result, brow_scores, question_enabled


def test_template_core_phrases():
    assert to_english(["HELLO", "QUESTION"]) == ("Hello, can I ask a question?", True)
    assert to_english(["WHERE", "BOOK"]) == ("Where is the book?", True)
    assert to_english(["PLEASE", "WAIT"]) == ("Please wait.", False)
    assert to_english([]) == ("", False)
    assert to_english(["REST"]) == ("", False)


def test_template_fallback_joins_words():
    text, q = to_english(["HOME", "HAPPY"])
    assert text == "Home happy." and q is False


def test_apply_question():
    assert apply_question("Water.", True) == "Water?"
    assert apply_question("Bye!", True) == "Bye?"
    assert apply_question("Water.", False) == "Water."
    assert apply_question("Why?", True) == "Why?"
    assert apply_question("", True) == ""


RAISED = {"browInnerUp": 0.8, "browOuterUpLeft": 0.7, "browOuterUpRight": 0.7, "browDownLeft": 0.0, "browDownRight": 0.0}
FURROW = {"browInnerUp": 0.0, "browDownLeft": 0.7, "browDownRight": 0.8}
NEUTRAL = {"browInnerUp": 0.1, "browDownLeft": 0.1, "browDownRight": 0.1}


def test_brow_scores():
    r, f = brow_scores(RAISED)
    assert r > 0.7 and f == 0.0
    assert brow_scores({}) == (0.0, 0.0)


def test_detector_yes_no_wh_and_none():
    d = QuestionDetector()
    for _ in range(6):
        d.push(RAISED)
    assert d.kind() == "yes_no" and d.decide() is True
    d.reset()
    for _ in range(6):
        d.push(FURROW)
    assert d.kind() == "wh" and d.decide() is True
    d.reset()
    for _ in range(6):
        d.push(NEUTRAL)
    assert d.decide() is False


def test_detector_needs_enough_face_frames_and_fraction():
    d = QuestionDetector()
    d.push(RAISED); d.push(None); d.push({})
    assert d.decide() is None
    for _ in range(9):
        d.push(NEUTRAL)
    assert d.decide() is False  # 1 raised frame out of 10 is a blip, not a question


def test_blendshapes_from_result_shapes():
    cat = lambda n, s: SimpleNamespace(category_name=n, score=s)
    flat = SimpleNamespace(face_blendshapes=[cat("browInnerUp", 0.5), cat("browDownLeft", 0.1)])
    nested = SimpleNamespace(face_blendshapes=[[cat("browInnerUp", 0.5)]])
    assert blendshapes_from_result(flat) == {"browInnerUp": 0.5, "browDownLeft": 0.1}
    assert blendshapes_from_result(nested) == {"browInnerUp": 0.5}
    assert blendshapes_from_result(SimpleNamespace(face_blendshapes=None)) is None
    assert blendshapes_from_result(object()) is None


def test_question_flag_behind_signer_flags():
    assert question_enabled({"SIGNER_FLAGS": "teach,question"})
    assert not question_enabled({"SIGNER_FLAGS": ""})
    assert not question_enabled({})
