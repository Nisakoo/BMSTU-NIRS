"""Compact lore context for the agent: bounded passages, never raw hits."""

from __future__ import annotations

import re
from typing import Literal

from smeshariki_ai.rag.lore.models import (
    LoreHit,
    LoreModel,
    LoreSearchResult,
)
from smeshariki_ai.rag.lore.stopwords import STOP_WORDS

ContextStatus = Literal["found", "empty"]

EMPTY_MESSAGE = (
    "В лоре нет подходящих фрагментов. Продолжай по идее пользователя и не "
    "выдавай придуманные факты за канонические."
)

# A clipped passage shorter than this is not worth showing to the model.
MIN_PASSAGE_CHARS = 80
# Sentence ends that allow a clean cut: ``.``, ``!``, ``?`` and ``…``.
_SENTENCE_END = re.compile(r"[.!?…](?=\s)")

# Character names alone do not describe a story premise. They are lemmatized
# by ``MorphAnalyzer`` (``Кроша`` → ``крош``, ``Ёжика`` → ``ежик``).
CHARACTER_NAME_TERMS = frozenset(
    {
        "бараш",
        "ежик",
        "карыч",
        "кар-карыч",
        "копатыч",
        "крош",
        "лосяш",
        "нюша",
        "пин",
        "совунья",
    }
)
# Function words never make a query meaningful on their own. The list lives in
# ``stopwords`` so the analyzer and the context rule share one source.
NON_CONTENT_TERMS = STOP_WORDS


class LorePassage(LoreModel):
    title: str
    source: str | None = None
    text: str


class LoreContext(LoreModel):
    status: ContextStatus
    passages: tuple[LorePassage, ...] = ()
    message: str | None = None


class LoreContextBuilder:
    """Turns search hits into a small reference block for the model.

    The builder deliberately drops scores and internal ids: the model needs
    text and a human-readable source, not ranking data or database keys.
    ``select`` keeps them for internal consumers, such as the offline
    benchmark, so both use one selection path.
    """

    def __init__(
        self,
        *,
        retrieval_k: int = 10,
        max_passages: int = 3,
        max_chars: int = 1600,
        min_score: float = 2.0,
    ) -> None:
        if retrieval_k <= 0:
            raise ValueError("retrieval_k must be positive")
        if max_passages <= 0:
            raise ValueError("max_passages must be positive")
        if max_chars <= 0:
            raise ValueError("max_chars must be positive")
        if min_score < 0:
            raise ValueError("min_score must not be negative")
        self.retrieval_k = retrieval_k
        self._max_passages = max_passages
        self._max_chars = max_chars
        self._min_score = min_score

    def select(
        self,
        result: LoreSearchResult,
        query_terms: tuple[str, ...] = (),
    ) -> tuple[tuple[LoreHit, str], ...]:
        """Selected ``(hit, final text)`` pairs the agent context is built from."""

        if query_terms and not _has_content_term(query_terms):
            return ()
        if not result.hits:
            return ()

        selected: list[tuple[LoreHit, str]] = []
        seen_documents: set[str] = set()
        used = 0

        for hit in result.hits:
            if len(selected) >= self._max_passages:
                break
            if hit.document_id in seen_documents:
                continue
            if hit.score < self._min_score:
                break

            remaining = self._max_chars - used
            if remaining <= 0:
                break
            text = hit.text.strip()
            if not text:
                continue
            if len(text) > remaining:
                clipped = _clip_to_budget(text, remaining)
                if clipped is None:
                    break
                text = clipped

            selected.append((hit, text))
            seen_documents.add(hit.document_id)
            used += len(text)

        return tuple(selected)

    def build(
        self,
        result: LoreSearchResult,
        query_terms: tuple[str, ...] = (),
    ) -> LoreContext:
        selected = self.select(result, query_terms)
        if not selected:
            return LoreContext(status="empty", message=EMPTY_MESSAGE)
        return LoreContext(
            status="found",
            passages=tuple(
                LorePassage(title=hit.title, source=hit.source, text=text)
                for hit, text in selected
            ),
        )


def _has_content_term(terms: tuple[str, ...]) -> bool:
    """A query made only of names and function words is not a premise."""

    return any(
        term not in CHARACTER_NAME_TERMS and term not in NON_CONTENT_TERMS
        for term in terms
    )


def _clip_to_budget(text: str, limit: int) -> str | None:
    """Cut a passage at a sentence end, or at a word end when unavoidable.

    ``None`` means nothing meaningful fits into the remaining budget: the
    builder stops instead of appending a one-word stub.
    """

    if limit <= 1:
        return None
    window = text[: limit - 1]
    sentence_end = None
    for match in _SENTENCE_END.finditer(window):
        sentence_end = match.end()
    if sentence_end is not None and sentence_end >= MIN_PASSAGE_CHARS:
        return window[:sentence_end].rstrip()
    space = window.rfind(" ")
    if space >= MIN_PASSAGE_CHARS:
        return f"{window[:space].rstrip()}…"
    # Last resort for tiny budgets and texts without spaces: the caller still
    # gets the strongest passage, cut at the budget, rather than nothing.
    stripped = window.rstrip()
    return None if not stripped else f"{stripped}…"


__all__ = [
    "CHARACTER_NAME_TERMS",
    "EMPTY_MESSAGE",
    "NON_CONTENT_TERMS",
    "ContextStatus",
    "LoreContext",
    "LoreContextBuilder",
    "LorePassage",
]
