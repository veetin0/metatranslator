"""Gloss sequence -> English. Template mode always works offline; fluent mode (SIGNER_LLM=haiku or
SIGNER_FLAGS=llm) sends only gloss text to Claude Haiku 4.5, validates the reply, and falls back to the template.

    from signer_core.language import to_english, fluent
    to_english(["WHERE", "BOOK"])   # ("Where is the book?", True)
    fluent(["WHERE", "BOOK"])       # Fluent(text=..., question=True, mode="template"|"llm", reason=...)
"""
from .llm import Fluent, FluentTranslator, apply_question, build_prompt, fluent, llm_enabled
from .template import ENGLISH, PHRASES, QUESTION_GLOSSES, read_english, to_english
from .validator import FUNCTION_WORDS, licensed_words, unlicensed, validate

__all__ = [
    "ENGLISH", "FUNCTION_WORDS", "Fluent", "FluentTranslator", "PHRASES", "QUESTION_GLOSSES", "apply_question",
    "build_prompt", "fluent", "licensed_words", "llm_enabled", "read_english", "to_english", "unlicensed", "validate",
]
