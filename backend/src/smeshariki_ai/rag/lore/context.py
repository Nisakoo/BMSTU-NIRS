"""Compact lore context for the agent: bounded passages, never raw hits."""

from __future__ import annotations

from typing import Literal

from smeshariki_ai.rag.lore.models import (
    LoreModel,
    LoreSearchResult,
)

ContextStatus = Literal["found", "empty"]

EMPTY_MESSAGE = (
    "В лоре нет подходящих фрагментов. Продолжай по идее пользователя и не "
    "выдавай придуманные факты за канонические."
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
    """

    def __init__(
        self,
        *,
        retrieval_k: int = 10,
        max_passages: int = 3,
        max_chars: int = 1600,
        score_ratio: float = 0.5,
    ) -> None:
        if retrieval_k <= 0:
            raise ValueError("retrieval_k must be positive")
        if max_passages <= 0:
            raise ValueError("max_passages must be positive")
        if max_chars <= 0:
            raise ValueError("max_chars must be positive")
        if not 0 <= score_ratio <= 1:
            raise ValueError("score_ratio must be between 0 and 1")
        self.retrieval_k = retrieval_k
        self._max_passages = max_passages
        self._max_chars = max_chars
        self._score_ratio = score_ratio

    def build(self, result: LoreSearchResult) -> LoreContext:
        if not result.hits:
            return LoreContext(status="empty", message=EMPTY_MESSAGE)

        threshold = result.hits[0].score * self._score_ratio
        passages: list[LorePassage] = []
        seen_documents: set[str] = set()
        used = 0

        for hit in result.hits:
            if len(passages) >= self._max_passages:
                break
            if hit.document_id in seen_documents:
                continue
            if hit.score < threshold:
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

            passages.append(
                LorePassage(
                    title=hit.title,
                    source=hit.source,
                    text=text,
                )
            )
            seen_documents.add(hit.document_id)
            used += len(text)

        if not passages:
            return LoreContext(status="empty", message=EMPTY_MESSAGE)
        return LoreContext(status="found", passages=tuple(passages))


__all__ = [
    "EMPTY_MESSAGE",
    "ContextStatus",
    "LoreContext",
    "LoreContextBuilder",
    "LorePassage",
]
