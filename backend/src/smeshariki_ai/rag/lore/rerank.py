"""Reranking of lore candidates: cheap recall first, careful ordering second.

BM25 gives a wide candidate list; the agent sees only three passages. A
reranker reorders (and trims) those candidates so the model reads the most
useful fragments. The adapter uses the same ``LLMProvider`` abstraction as the
agent and degrades to the original order on any failure.
"""

from __future__ import annotations

import logging
import re
import time
from abc import ABC, abstractmethod
from collections.abc import Sequence

from smeshariki_ai.agent import (
    LLMProvider,
    LLMProviderError,
    LLMResponse,
    Message,
    MessageRole,
)
from smeshariki_ai.observability import log_event, utc_now
from smeshariki_ai.rag.lore.models import LoreHit

logger = logging.getLogger(__name__)

RERANK_PROMPT = (
    "Ниже вопрос и пронумерованные фрагменты текста. Верни через запятую только "
    "номера фрагментов, которые действительно помогают ответить на вопрос, в "
    "порядке убывания полезности. Если ни один фрагмент не помогает, верни 0. "
    "Не добавляй пояснений, текста и знаков кроме номеров и запятых."
)

_PASSAGE_CHARS = 400
_NUMBER = re.compile(r"\d+")


class Ranker(ABC):
    @abstractmethod
    async def rerank(
        self,
        query: str,
        hits: Sequence[LoreHit],
        *,
        limit: int,
    ) -> tuple[LoreHit, ...]:
        """Return at most ``limit`` hits ordered by usefulness."""


class NoopRanker(Ranker):
    """Keeps the retrieval order; useful as an explicit default."""

    async def rerank(
        self,
        query: str,
        hits: Sequence[LoreHit],
        *,
        limit: int,
    ) -> tuple[LoreHit, ...]:
        return tuple(hits[:limit])


def parse_ranking(text: str, *, total: int) -> tuple[int, ...]:
    """Turn a model answer into 1-based passage numbers within ``total``."""

    if total <= 0:
        return ()
    numbers: list[int] = []
    for match in _NUMBER.finditer(text):
        number = int(match.group(0))
        if 1 <= number <= total and number not in numbers:
            numbers.append(number)
    return tuple(numbers)


def dedupe_documents(
    hits: Sequence[LoreHit],
    *,
    limit: int,
) -> tuple[LoreHit, ...]:
    """Keep the first (best-scoring) chunk of each document.

    The agent receives at most one passage per document, so reranking chunks of
    the same document wastes the candidate window.
    """

    seen: set[str] = set()
    unique: list[LoreHit] = []
    for hit in hits:
        if hit.document_id in seen:
            continue
        seen.add(hit.document_id)
        unique.append(hit)
        if len(unique) >= limit:
            break
    return tuple(unique)


def _prompt(query: str, hits: Sequence[LoreHit]) -> str:
    lines = [RERANK_PROMPT, "", f"Вопрос: {query}", "", "Фрагменты:"]
    for position, hit in enumerate(hits, start=1):
        text = hit.text.strip()
        if len(text) > _PASSAGE_CHARS:
            text = f"{text[:_PASSAGE_CHARS].rstrip()}…"
        lines.append(f"{position}. {hit.title}: {text}")
    return "\n".join(lines)


class LLMReranker(Ranker):
    def __init__(self, provider: LLMProvider) -> None:
        self._provider = provider

    async def rerank(
        self,
        query: str,
        hits: Sequence[LoreHit],
        *,
        limit: int,
    ) -> tuple[LoreHit, ...]:
        if limit <= 0 or len(hits) <= 1:
            return tuple(hits[: max(limit, 0)])
        started_at = utc_now()
        started = time.monotonic()
        try:
            response: LLMResponse | None = None
            async for event in self._provider.stream(
                (
                    Message(role=MessageRole.SYSTEM, content=RERANK_PROMPT),
                    Message(role=MessageRole.USER, content=_prompt(query, hits)),
                ),
                (),
            ):
                if isinstance(event, LLMResponse):
                    response = event
        except LLMProviderError as error:
            self._log(started_at, started, outcome="failed", count=0, error=error)
            return tuple(hits[:limit])

        content = (
            "" if response is None or response.content is None else response.content
        )
        order = parse_ranking(content, total=len(hits))
        if not order:
            self._log(started_at, started, outcome="unparsed", count=0)
            return tuple(hits[:limit])

        # Chosen passages first, the rest afterwards: a reranker must never
        # reduce recall below the candidate set by dropping everything.
        chosen = [hits[number - 1] for number in order]
        chosen_ids = {id(hit) for hit in chosen}
        rest = [hit for hit in hits if id(hit) not in chosen_ids]
        result = tuple((chosen + rest)[:limit])
        self._log(started_at, started, outcome="reranked", count=len(chosen))
        return result

    @staticmethod
    def _log(
        started_at: str,
        started: float,
        *,
        outcome: str,
        count: int,
        error: Exception | None = None,
    ) -> None:
        log_event(
            logger,
            logging.WARNING if error is not None else logging.INFO,
            "lore.rerank.completed",
            started_at=started_at,
            duration_ms=round((time.monotonic() - started) * 1000, 3),
            outcome=outcome,
            passage_count=count,
            error_type=None if error is None else type(error).__name__,
        )


__all__ = [
    "LLMReranker",
    "NoopRanker",
    "RERANK_PROMPT",
    "Ranker",
    "dedupe_documents",
    "parse_ranking",
]
