"""Compact lore context for the agent: bounded passages, never raw hits."""

from __future__ import annotations

from typing import Literal

from smeshariki_ai.rag.lore.models import (
    LoreHit,
    LoreModel,
    LoreSearchResult,
)

ContextStatus = Literal["found", "empty"]

EMPTY_MESSAGE = (
    "В лоре нет подходящих фрагментов. Продолжай по идее пользователя и не "
    "выдавай придуманные факты за канонические."
)

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
# Function words never make a query meaningful on their own.
NON_CONTENT_TERMS = frozenset(
    {
        "а",
        "без",
        "бы",
        "был",
        "была",
        "были",
        "было",
        "быть",
        "в",
        "во",
        "вот",
        "все",
        "всё",
        "вы",
        "где",
        "да",
        "для",
        "до",
        "его",
        "ее",
        "её",
        "ей",
        "ему",
        "если",
        "есть",
        "же",
        "за",
        "и",
        "из",
        "или",
        "им",
        "их",
        "к",
        "как",
        "ко",
        "когда",
        "кто",
        "ли",
        "мне",
        "мы",
        "на",
        "над",
        "не",
        "него",
        "нее",
        "неё",
        "нет",
        "ни",
        "но",
        "ну",
        "о",
        "об",
        "от",
        "по",
        "под",
        "при",
        "про",
        "с",
        "со",
        "так",
        "там",
        "то",
        "тоже",
        "тут",
        "у",
        "уже",
        "что",
        "чтобы",
        "это",
        "я",
    }
)


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
                if remaining == 1:
                    break
                text = text[: remaining - 1].rstrip() + "…"

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


__all__ = [
    "CHARACTER_NAME_TERMS",
    "EMPTY_MESSAGE",
    "NON_CONTENT_TERMS",
    "ContextStatus",
    "LoreContext",
    "LoreContextBuilder",
    "LorePassage",
]
