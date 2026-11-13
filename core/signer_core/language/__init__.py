"""Gloss sequence -> English (M1: template mode; SIGNER_LLM=haiku comes later and only ever sends gloss text).

    from signer_core.language import to_english
    to_english(["WHERE", "BOOK"])   # ("Where is the book?", True)
"""
from .template import ENGLISH, PHRASES, QUESTION_GLOSSES, read_english, to_english

__all__ = ["ENGLISH", "PHRASES", "QUESTION_GLOSSES", "read_english", "to_english"]
