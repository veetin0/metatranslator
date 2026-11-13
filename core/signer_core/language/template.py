"""Template gloss -> English (mode "template"): phrase rules for the 24-sign vocabulary, then a word fallback.

ASL word order is topic-comment and drops "is"/"the"; the templates add them for the common short sentences
(VOCAB.md notes: HELLO QUESTION, WHERE BOOK, PLEASE WAIT, HELP, THANKYOU BYE). Anything unmatched becomes the
English words joined in order, capitalised and punctuated, so the output is always readable and never invents
content that was not signed.
"""
from __future__ import annotations

import re
from pathlib import Path

WH = ("WHERE", "WHY", "WHO")
QUESTION_GLOSSES = frozenset({"WHERE", "WHY", "WHO", "QUESTION"})

# Default display text (data/VOCAB.md `english`); read_english() reloads it from the file when present.
ENGLISH = {
    "HELLO": "hello", "BYE": "bye", "YES": "yes", "NO": "no", "PLEASE": "please", "THANKYOU": "thank you",
    "WAIT": "wait", "FINISH": "finished", "POTTY": "bathroom", "WATER": "water", "WHERE": "where", "WHY": "why",
    "WHO": "who", "TIME": "time", "BOOK": "book", "LISTEN": "listen", "TALK": "talk", "HOME": "home",
    "SICK": "sick", "HAPPY": "happy", "HELP": "help", "QUESTION": "question", "UNDERSTAND": "understand",
    "AGAIN": "again",
}

NOUNS = {"WATER", "BOOK", "HOME", "POTTY", "TIME"}

# Whole-phrase templates, longest match first (keys are gloss tuples).
PHRASES: dict[tuple[str, ...], str] = {
    ("HELLO", "QUESTION"): "Hello, can I ask a question?",
    ("QUESTION",): "Can I ask a question?",
    ("PLEASE", "WAIT"): "Please wait.",
    ("WAIT", "PLEASE"): "Please wait.",
    ("PLEASE", "HELP"): "Please help me.",
    ("HELP", "PLEASE"): "Please help me.",
    ("HELP",): "I need help.",
    ("THANKYOU", "BYE"): "Thank you, bye!",
    ("TIME",): "What time is it?",
    ("UNDERSTAND",): "I understand.",
    ("NO", "UNDERSTAND"): "I don't understand.",
    ("UNDERSTAND", "NO"): "I don't understand.",
    ("AGAIN",): "Again, please.",
    ("AGAIN", "PLEASE"): "Can you say that again, please?",
    ("PLEASE", "AGAIN"): "Can you say that again, please?",
    ("FINISH",): "I'm finished.",
    ("SICK",): "I feel sick.",
    ("HAPPY",): "I'm happy.",
    ("WATER", "PLEASE"): "Water, please.",
    ("PLEASE", "WATER"): "Water, please.",
    ("WHERE", "POTTY"): "Where is the bathroom?",
    ("POTTY", "WHERE"): "Where is the bathroom?",
    ("LISTEN",): "I'm listening.",
    ("THANKYOU",): "Thank you.",
    ("HELLO",): "Hello.",
    ("BYE",): "Bye!",
    ("YES",): "Yes.",
    ("NO",): "No.",
    ("PLEASE",): "Please.",
    ("WAIT",): "Wait.",
}


def read_english(vocab_path: str | Path) -> dict[str, str]:
    """GLOSS -> english from data/VOCAB.md (falls back to the built-in table for missing rows)."""
    out = dict(ENGLISH)
    p = Path(vocab_path)
    if not p.exists():
        return out
    for line in p.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^\|\s*([A-Z][A-Z0-9_]*)\s*\|\s*([^|]+?)\s*\|", line)
        if m and m.group(1) not in ("GLOSS", "REST"):
            out[m.group(1)] = m.group(2)
    return out


def _sentence(words: list[str], question: bool) -> str:
    s = " ".join(w for w in words if w).strip()
    if not s:
        return ""
    return s[0].upper() + s[1:] + ("?" if question else ".")


def _wh(gloss: list[str], english: dict[str, str]) -> str | None:
    """WHERE BOOK / BOOK WHERE -> 'Where is the book?'; WHO / WHY alone -> 'Who?' / 'Why?'."""
    whs = [g for g in gloss if g in WH]
    if len(whs) != 1:
        return None
    wh = whs[0]
    rest = [g for g in gloss if g != wh]
    if not rest:
        return english.get(wh, wh.lower()).capitalize() + "?"
    if len(rest) == 1 and rest[0] in NOUNS and wh == "WHERE":
        return f"Where is the {english.get(rest[0], rest[0].lower())}?"
    if len(rest) == 1 and wh == "WHO":
        return f"Who is {english.get(rest[0], rest[0].lower())}?" if rest[0] in ("SICK", "HAPPY") else None
    return None


def _match(gloss: list[str]) -> str | None:
    return PHRASES.get(tuple(gloss))


def to_english(gloss: list[str], english: dict[str, str] | None = None) -> tuple[str, bool]:
    """Gloss sequence -> (English sentence, question flag). Empty input -> ('', False)."""
    english = english or ENGLISH
    gloss = [g for g in gloss if g and g != "REST"]
    if not gloss:
        return "", False
    question = any(g in QUESTION_GLOSSES for g in gloss) or gloss == ["TIME"]
    text = _match(gloss) or _wh(gloss, english)
    if text:
        return text, question or text.endswith("?")
    # Split a leading greeting / trailing thanks off the core phrase: HELLO WHERE BOOK -> "Hello, where is the book?"
    head, tail = [], []
    while gloss and gloss[0] in ("HELLO",):
        head.append(gloss.pop(0))
    while gloss and gloss[-1] in ("THANKYOU", "BYE", "PLEASE") and len(gloss) > 1:
        tail.insert(0, gloss.pop())
    core = _match(gloss) or _wh(gloss, english) if gloss else ""
    if not core:
        core = _sentence([english.get(g, g.lower()) for g in gloss], question)
    if head and core:
        keep = core.startswith(("I ", "I'"))
        core = "Hello, " + (core if keep else core[0].lower() + core[1:])
    elif head:
        core = "Hello."
    if tail:
        words = ", ".join(english.get(g, g.lower()) for g in tail)
        end = core[-1] if core else "."
        core = (core[:-1] + ", " + words + end) if core else _sentence([words], question)
    return core, question or core.endswith("?")
