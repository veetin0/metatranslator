"""Fluent mode (SIGNER_LLM=haiku): Claude Haiku 4.5 rephrases the *gloss text only* into one natural sentence.

Privacy: the request contains nothing but the gloss words (e.g. "HELLO QUESTION(unsure)") and, when the face says
so, the word that it is a question. Never video, frames, landmarks or ids.

Safety: every reply goes through `validator.validate`; a sentence that adds a content word the glosses do not
license is dropped and the offline template is used instead. Same fallback with no API key, no `anthropic`
package, a network error, a timeout or a refusal, so the caption path never blocks on the network.

    from signer_core.language import fluent
    fluent(["WHERE", "BOOK"])   # Fluent(text="Where is the book?", question=True, mode="template", reason="off")
"""
from __future__ import annotations

import os
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from .template import ENGLISH, to_english
from .validator import validate

DEFAULT_MODEL = "claude-haiku-4-5-20251001"  # CONTRACTS §9 SIGNER_LLM_MODEL
DEFAULT_TIMEOUT_S = 2.5

SYSTEM = (
    "You turn American Sign Language gloss sequences into one short, natural English sentence for a live caption. "
    "Rules: use only the meaning of the given glosses; do not add any new noun, verb, adjective, name, number, "
    "place or fact; you may add small grammar words (a, the, is, I, you, can, to...) and reorder words. "
    "Glosses marked (unsure) were recognised with low confidence: keep them, do not guess alternatives. "
    "If told it is a question, end with a question mark. "
    "Reply with the sentence only: no quotes, no explanation, at most 12 words."
)


@dataclass(frozen=True)
class Fluent:
    text: str
    question: bool
    mode: str  # "llm" | "template"  (CaptionEvent.mode)
    reason: str  # "llm" | "off" | "no_key" | "no_sdk" | "error" | "rejected:<words>" | "empty"


def flags(env: Mapping[str, str] | None = None) -> set[str]:
    env = os.environ if env is None else env
    return {f.strip().lower() for f in env.get("SIGNER_FLAGS", "").split(",") if f.strip()}


def llm_enabled(env: Mapping[str, str] | None = None) -> bool:
    """Fluent mode is on when SIGNER_LLM=haiku or the `llm` graft flag is set."""
    env = os.environ if env is None else env
    return env.get("SIGNER_LLM", "off").strip().lower() == "haiku" or "llm" in flags(env)


def apply_question(text: str, question: bool) -> str:
    """Make the punctuation agree with the question flag (face blendshapes can turn 'Water.' into 'Water?')."""
    if not text or not question or text.endswith("?"):
        return text
    return (text[:-1] if text[-1] in ".!" else text) + "?"


def build_prompt(gloss: list[str], unsure: Iterable[str] = (), question: bool = False) -> str:
    """The exact user message sent to the model: gloss words only."""
    unsure = set(unsure)
    words = " ".join(f"{g}(unsure)" if g in unsure else g for g in gloss)
    return f"Glosses: {words}" + ("\nIt is a question." if question else "")


def _clean(reply: str) -> str:
    s = (reply or "").strip().strip('"').strip("“”").strip()
    return s.splitlines()[0].strip() if s else ""


class HaikuClient:
    """Thin wrapper over the Anthropic SDK; `complete(prompt) -> str`. Raises on any failure."""

    def __init__(self, api_key: str, model: str = DEFAULT_MODEL, timeout_s: float = DEFAULT_TIMEOUT_S):
        import anthropic  # lazy: core works without the package

        self.model = model
        self._client = anthropic.Anthropic(api_key=api_key, timeout=timeout_s, max_retries=0)

    def complete(self, prompt: str) -> str:
        msg = self._client.messages.create(
            model=self.model,
            max_tokens=64,
            system=SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )
        if getattr(msg, "stop_reason", None) == "refusal":
            raise RuntimeError("refusal")
        return "".join(getattr(b, "text", "") for b in msg.content if getattr(b, "type", "") == "text")


def make_client(env: Mapping[str, str] | None = None) -> tuple[Any | None, str]:
    """(client, reason). No key -> (None, 'no_key'); no SDK -> (None, 'no_sdk')."""
    env = os.environ if env is None else env
    key = env.get("ANTHROPIC_API_KEY", "").strip()
    if not key:
        return None, "no_key"
    try:
        timeout = float(env.get("SIGNER_LLM_TIMEOUT_S", DEFAULT_TIMEOUT_S))
        return HaikuClient(key, env.get("SIGNER_LLM_MODEL", DEFAULT_MODEL) or DEFAULT_MODEL, timeout), "ok"
    except ImportError:
        return None, "no_sdk"
    except Exception:
        return None, "error"


class FluentTranslator:
    """Gloss -> Fluent with an LRU cache (same signed phrase -> one API call)."""

    def __init__(self, client: Any | None = None, env: Mapping[str, str] | None = None,
                 english: dict[str, str] | None = None, cache_size: int = 256):
        self.env = os.environ if env is None else env
        self.english = english or ENGLISH
        self.enabled = llm_enabled(self.env)
        if client is not None:
            self.client, self.client_reason = client, "ok"
        elif self.enabled:
            self.client, self.client_reason = make_client(self.env)
        else:
            self.client, self.client_reason = None, "off"
        self._cache: OrderedDict[tuple, Fluent] = OrderedDict()
        self._cache_size = cache_size

    def _template(self, gloss: list[str], question_hint: bool | None, reason: str) -> Fluent:
        text, q = to_english(gloss, self.english)
        q = bool(q or question_hint)
        return Fluent(apply_question(text, q), q, "template", reason)

    def __call__(self, gloss: Iterable[str], unsure: Iterable[str] = (), question_hint: bool | None = None) -> Fluent:
        gloss = [g for g in gloss if g and g != "REST"]
        if not gloss:
            return Fluent("", False, "template", "empty")
        if not self.enabled:
            return self._template(gloss, question_hint, "off")
        if self.client is None:
            return self._template(gloss, question_hint, self.client_reason)
        unsure = tuple(sorted(set(unsure) & set(gloss)))
        key = (tuple(gloss), unsure, bool(question_hint))
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]
        _, template_q = to_english(gloss, self.english)
        q = bool(template_q or question_hint)
        try:
            reply = _clean(self.client.complete(build_prompt(gloss, unsure, q)))
        except Exception:
            return self._template(gloss, question_hint, "error")  # not cached: the network may come back
        ok, bad = validate(reply, gloss, self.english)
        if not ok:
            out = self._template(gloss, question_hint, "rejected:" + ",".join(bad))
        else:
            q = q or reply.endswith("?")
            out = Fluent(apply_question(reply, q), q, "llm", "llm")
        self._cache[key] = out
        if len(self._cache) > self._cache_size:
            self._cache.popitem(last=False)
        return out


_default: FluentTranslator | None = None


def fluent(gloss: Iterable[str], unsure: Iterable[str] = (), question_hint: bool | None = None,
           english: dict[str, str] | None = None) -> Fluent:
    """Module-level convenience using env config (built once; call `reset()` after changing env)."""
    global _default
    if _default is None or (english is not None and english is not _default.english):
        _default = FluentTranslator(english=english)
    return _default(gloss, unsure, question_hint)


def reset() -> None:
    global _default
    _default = None
