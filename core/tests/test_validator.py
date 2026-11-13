"""D2: the gloss-only validator rejects added content words; fluent mode falls back to the template offline."""
import pytest

from signer_core.language import ENGLISH, FluentTranslator, PHRASES, build_prompt, to_english, validate
from signer_core.language.llm import llm_enabled


class FakeClient:
    def __init__(self, reply=None, exc=None):
        self.reply, self.exc, self.prompts = reply, exc, []

    def complete(self, prompt):
        self.prompts.append(prompt)
        if self.exc:
            raise self.exc
        return self.reply


HAIKU = {"SIGNER_LLM": "haiku", "ANTHROPIC_API_KEY": "test-key"}


# --- validator ---------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("gloss,sentence", [
    (["WHERE", "BOOK"], "Where is the book?"),
    (["WHERE", "BOOK"], "Where's my book?"),
    (["HELLO", "QUESTION"], "Hi, can I ask you a question?"),
    (["THANKYOU", "BYE"], "Thanks, goodbye!"),
    (["POTTY", "WHERE"], "Where is the restroom?"),
    (["NO", "UNDERSTAND"], "I don't understand."),
    (["PLEASE", "WAIT"], "Please wait a moment."),
    (["HELP", "PLEASE"], "Please, I need help."),
    (["SICK"], "I feel sick."),
    (["FINISH"], "I'm done."),
])
def test_validator_accepts_rephrasings(gloss, sentence):
    ok, bad = validate(sentence, gloss)
    assert ok, bad


@pytest.mark.parametrize("gloss,sentence,word", [
    (["WHERE", "BOOK"], "Where is the red book?", "red"),
    (["WHERE", "BOOK"], "Where is the library?", "library"),
    (["WATER", "PLEASE"], "Coffee, please.", "coffee"),
    (["HELP"], "I need a doctor.", "doctor"),
    (["TIME"], "Is it 5 o'clock?", "5"),
    (["HELLO"], "Hello, John.", "john"),
    (["SICK"], "I feel sick, call an ambulance.", "call"),
    (["BOOK"], "Page 12 of the book.", "page"),
])
def test_validator_rejects_added_content_word(gloss, sentence, word):
    ok, bad = validate(sentence, gloss)
    assert not ok
    assert word in bad


def test_validator_rejects_empty_and_run_on():
    assert validate("", ["HELLO"])[0] is False
    assert validate("Hello.", [])[0] is False
    assert validate("Hello " * 30, ["HELLO"])[0] is False
    assert validate("Hello.\nHello.", ["HELLO"])[0] is False


def test_every_template_phrase_passes_its_own_validator():
    for gloss in PHRASES:
        text, _ = to_english(list(gloss))
        assert validate(text, list(gloss))[0], (gloss, text)


def test_every_single_sign_template_passes():
    for g in ENGLISH:
        text, _ = to_english([g])
        assert validate(text, [g])[0], (g, text)


# --- fluent mode ---------------------------------------------------------------------------------------------------

def test_offline_haiku_without_key_uses_template():
    t = FluentTranslator(env={"SIGNER_LLM": "haiku"})
    out = t(["WHERE", "BOOK"])
    assert out.mode == "template" and out.reason == "no_key"
    assert out.text == "Where is the book?" and out.question is True


def test_llm_off_by_default_uses_template_and_never_calls_client():
    assert not llm_enabled({})
    t = FluentTranslator(env={"ANTHROPIC_API_KEY": "k"})
    out = t(["HELLO"])
    assert out.mode == "template" and out.reason == "off" and out.text == "Hello."


def test_flag_llm_enables_fluent_mode():
    assert llm_enabled({"SIGNER_FLAGS": "teach, llm"})


def test_valid_llm_reply_is_used():
    c = FakeClient("Hi, can I ask you a question?")
    out = FluentTranslator(client=c, env=HAIKU)(["HELLO", "QUESTION"])
    assert out.mode == "llm" and out.text == "Hi, can I ask you a question?" and out.question is True


def test_llm_reply_adding_content_falls_back_to_template():
    c = FakeClient("Where is the library book?")
    out = FluentTranslator(client=c, env=HAIKU)(["WHERE", "BOOK"])
    assert out.mode == "template" and out.text == "Where is the book?"
    assert out.reason.startswith("rejected:") and "library" in out.reason


def test_network_error_falls_back_and_is_not_cached():
    c = FakeClient(exc=ConnectionError("offline"))
    t = FluentTranslator(client=c, env=HAIKU)
    assert t(["HELP"]).mode == "template"
    c.exc, c.reply = None, "I need help."
    assert t(["HELP"]).mode == "llm"


def test_only_gloss_text_is_sent():
    c = FakeClient("Where is the book?")
    FluentTranslator(client=c, env=HAIKU)(["WHERE", "BOOK"], unsure=["BOOK"])
    assert c.prompts == ["Glosses: WHERE BOOK(unsure)\nIt is a question."]
    assert build_prompt(["HELLO"]) == "Glosses: HELLO"


def test_cache_avoids_repeat_calls():
    c = FakeClient("Hello.")
    t = FluentTranslator(client=c, env=HAIKU)
    t(["HELLO"]); t(["HELLO"])
    assert len(c.prompts) == 1


def test_question_hint_from_face_sets_flag_and_punctuation():
    t = FluentTranslator(env={})
    out = t(["WATER"], question_hint=True)
    assert out.question is True and out.text.endswith("?")
    c = FakeClient("Water, please.")
    out = FluentTranslator(client=c, env=HAIKU)(["WATER", "PLEASE"], question_hint=True)
    assert out.mode == "llm" and out.text == "Water, please?" and out.question is True
    assert c.prompts[0].endswith("It is a question.")


def test_empty_gloss():
    out = FluentTranslator(env=HAIKU)(["REST"])
    assert out.text == "" and out.reason == "empty"
