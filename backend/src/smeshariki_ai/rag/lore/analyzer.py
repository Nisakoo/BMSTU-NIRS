"""Text analysis used by the BM25 index.

The analyzer is a port: the index and use cases do not depend on a particular
morphology library. ``SimpleAnalyzer`` is deterministic and dependency-free;
``MorphAnalyzer`` adds Russian lemmatization through ``pymorphy3``. Both drop
stop words, so a document and a query are filtered the same way.
"""

from __future__ import annotations

import re
import unicodedata
from abc import ABC, abstractmethod

import pymorphy3

from smeshariki_ai.rag.lore.stopwords import drop_stop_words

_TOKEN = re.compile(r"[a-zа-я0-9]+(?:-[a-zа-я0-9]+)*")


class TextAnalyzer(ABC):
    @abstractmethod
    def terms(self, text: str) -> tuple[str, ...]:
        """Return normalized index terms in their original order."""


def normalize_text(text: str) -> str:
    """NFC, case folding, whitespace collapse and ``ё``/``е`` equivalence."""

    folded = unicodedata.normalize("NFC", text).casefold().replace("ё", "е")
    return " ".join(folded.split())


def _tokens(text: str) -> tuple[str, ...]:
    return tuple(match.group(0) for match in _TOKEN.finditer(normalize_text(text)))


class SimpleAnalyzer(TextAnalyzer):
    """Lowercase word tokens without morphology; useful for tests and baselines."""

    def terms(self, text: str) -> tuple[str, ...]:
        return drop_stop_words(_tokens(text))


class MorphAnalyzer(TextAnalyzer):
    """Russian lemmatization for documents and queries.

    Hyphenated names are kept whole, so ``Кар-Карыч`` remains one term and is
    not distorted by lemmatizing its parts. Unknown words and names are kept as
    written instead of being dropped.
    """

    def __init__(self) -> None:
        self._morph = pymorphy3.MorphAnalyzer()

    def terms(self, text: str) -> tuple[str, ...]:
        return drop_stop_words(self._normal_form(token) for token in _tokens(text))

    def _normal_form(self, token: str) -> str:
        if "-" in token:
            return token
        try:
            normal_form = self._morph.parse(token)[0].normal_form
        except (IndexError, ValueError):
            return token
        return normalize_text(normal_form) or token
