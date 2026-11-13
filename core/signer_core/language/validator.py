"""Gloss-only validator: an LLM sentence may only rephrase what was signed, never add content.

A sentence passes when every word in it is either
  * a closed-class function word (articles, pronouns, auxiliaries, prepositions, conjunctions, politeness glue), or
  * licensed by one of the signed glosses: its English text (data/VOCAB.md), a few listed synonyms, simple
    inflections (-s, -ed, -ing, -ly), or a word the offline template itself uses for that gloss sequence.

Anything else (a new noun, verb, number, name, place...) is an unlicensed content word and the sentence is
rejected; the caller then falls back to the template. Numbers are never licensed.
"""
from __future__ import annotations

import re
from typing import Iterable

from .template import ENGLISH, to_english

# Closed-class words a fluent rephrasing may need. Deliberately no content verbs/nouns/adjectives
# (except the generic "need"/"want"/"ask"/"say"/"feel" kept OUT on purpose: they come only via GLOSS_EXTRA).
FUNCTION_WORDS = frozenset("""
a an the this that these those it its it's
i me my mine myself you your yours yourself we us our he him his she her they them their
is am are was were be been being do does did done don't doesn't didn't isn't aren't wasn't weren't
have has had having
can could will would shall should may might must can't cannot couldn't won't wouldn't
not no n't to of in on at for with from by about up down out off into onto over under
and or but so if then than as because
there here what where why who whom whose when which how
some any all just very too also really still now
oh ok okay well
i'm you're we're they're he's she's that's what's where's who's there's here's let's
i've you've we've they've i'll you'll we'll they'll i'd you'd we'd they'd
""".split())

# Extra words a gloss licenses beyond its VOCAB english (synonyms and the words the templates use).
GLOSS_EXTRA: dict[str, tuple[str, ...]] = {
    "HELLO": ("hi", "hey"),
    "BYE": ("goodbye", "see", "later"),
    "YES": ("yeah", "yep", "sure"),
    "NO": ("nope",),
    "PLEASE": (),
    "THANKYOU": ("thank", "thanks"),
    "WAIT": ("moment", "minute", "hold", "on"),
    "FINISH": ("finish", "done", "complete", "over"),
    "POTTY": ("bathroom", "restroom", "toilet", "potty"),
    "WATER": ("drink",),
    "TIME": ("clock",),
    "LISTEN": ("hear",),
    "TALK": ("speak", "say", "tell", "chat"),
    "HOME": ("house",),
    "SICK": ("ill", "unwell", "feel"),
    "HAPPY": ("glad",),
    "HELP": ("need",),
    "QUESTION": ("ask",),
    "UNDERSTAND": ("get",),
    "AGAIN": ("repeat", "say"),
}

_TOKEN = re.compile(r"[a-z0-9]+(?:'[a-z]+)?")


def tokens(text: str) -> list[str]:
    """Lower-case word tokens; curly apostrophes normalised; contractions kept whole ("don't")."""
    t = text.lower().replace("’", "'").replace("‘", "'")
    return _TOKEN.findall(t)


def _inflections(word: str) -> set[str]:
    w = word.lower()
    out = {w, w + "s", w + "es", w + "ed", w + "d", w + "ing", w + "ly"}
    if w.endswith("e"):
        out |= {w[:-1] + "ing", w + "d"}
    if w.endswith("y"):
        out |= {w[:-1] + "ies", w[:-1] + "ied"}
    if w.endswith("ed"):  # "finished" licenses "finish"
        out.add(w[:-2])
    return out


def licensed_words(gloss: Iterable[str], english: dict[str, str] | None = None) -> set[str]:
    """All content words the signed glosses license (function words not included)."""
    english = english or ENGLISH
    gloss = [g for g in gloss if g and g != "REST"]
    out: set[str] = set()
    for g in gloss:
        for phrase in (english.get(g, g.lower()), g.lower(), *GLOSS_EXTRA.get(g, ())):
            for w in tokens(phrase):
                out |= _inflections(w)
    template_text, _ = to_english(gloss, english)
    out |= set(tokens(template_text))
    return {w for w in out if not w.isdigit()}


def unlicensed(sentence: str, gloss: Iterable[str], english: dict[str, str] | None = None) -> list[str]:
    """Words in `sentence` that neither a gloss nor the function-word list licenses (in order, deduplicated)."""
    allowed = licensed_words(gloss, english) | FUNCTION_WORDS
    bad: list[str] = []
    for w in tokens(sentence):
        if w in allowed:
            continue
        # "book's" -> "book"; numbers are never licensed
        base = w.split("'")[0]
        if not w.isdigit() and base in allowed and not base.isdigit():
            continue
        if w not in bad:
            bad.append(w)
    return bad


MAX_WORDS_PER_GLOSS = 6


def validate(sentence: str, gloss: Iterable[str], english: dict[str, str] | None = None) -> tuple[bool, list[str]]:
    """(ok, offending words). Rejects empty text, unlicensed content words and run-on output."""
    gloss = [g for g in gloss if g and g != "REST"]
    s = (sentence or "").strip()
    if not s or not gloss:
        return False, []
    if "\n" in s or len(tokens(s)) > MAX_WORDS_PER_GLOSS * len(gloss) + 2:
        return False, ["<too long>"]
    bad = unlicensed(s, gloss, english)
    return (not bad), bad
