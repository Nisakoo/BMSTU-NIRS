"""Query expansion before BM25: a port, an LLM adapter and safe parsing."""

from __future__ import annotations

import logging
import re
import time
from abc import ABC, abstractmethod
from collections import OrderedDict
from collections.abc import Mapping

from smeshariki_ai.agent import (
    LLMProvider,
    LLMProviderError,
    LLMResponse,
    Message,
    MessageRole,
)
from smeshariki_ai.observability import log_event, utc_now

logger = logging.getLogger(__name__)

EXPANSION_PROMPT = (
    "Перепиши вопрос пользователя в набор ключевых слов для лексического поиска "
    "по эпизодам «Смешариков». Верни только слова через пробел, от 5 до 10, без "
    "пояснений, нумерации и знаков препинания. Добавь синонимы и конкретные "
    "предметы, имена и занятия, которые могут встречаться в сюжете."
)

_TOKEN = re.compile(r"[a-zа-яё0-9]+(?:-[a-zа-яё0-9]+)*")


class QueryExpander(ABC):
    @abstractmethod
    async def expand(self, query: str) -> tuple[str, ...]:
        """Return extra search terms; an empty tuple means no expansion."""


def parse_expansion(text: str, *, max_terms: int = 10) -> tuple[str, ...]:
    """Keep word tokens only: no numbering, punctuation or duplicates."""

    if max_terms <= 0:
        return ()
    tokens = (
        token
        for token in _TOKEN.findall(text.casefold())
        # A bare number is list numbering, not a search term.
        if token and any(character.isalpha() for character in token)
    )
    unique = dict.fromkeys(tokens)
    return tuple(list(unique)[:max_terms])


class LiteLLMQueryExpander(QueryExpander):
    """Expands a query with keywords produced by the configured LLM."""

    def __init__(self, provider: LLMProvider, *, max_terms: int = 10) -> None:
        if max_terms <= 0:
            raise ValueError("max_terms must be positive")
        self._provider = provider
        self._max_terms = max_terms

    async def expand(self, query: str) -> tuple[str, ...]:
        started_at = utc_now()
        started = time.monotonic()
        response: LLMResponse | None = None
        try:
            async for event in self._provider.stream(
                (
                    Message(role=MessageRole.SYSTEM, content=EXPANSION_PROMPT),
                    Message(role=MessageRole.USER, content=query),
                ),
                (),
            ):
                if isinstance(event, LLMResponse):
                    response = event
        except LLMProviderError as error:
            self._log(started_at, started, outcome="failed", terms=(), error=error)
            return ()

        content = (
            "" if response is None or response.content is None else response.content
        )
        terms = parse_expansion(content, max_terms=self._max_terms)
        self._log(
            started_at,
            started,
            outcome="expanded" if terms else "empty",
            terms=terms,
        )
        return terms

    @staticmethod
    def _log(
        started_at: str,
        started: float,
        *,
        outcome: str,
        terms: tuple[str, ...],
        error: Exception | None = None,
    ) -> None:
        # The query and the expanded terms never reach the journal.
        log_event(
            logger,
            logging.WARNING if error is not None else logging.INFO,
            "lore.query_expansion.completed",
            started_at=started_at,
            duration_ms=round((time.monotonic() - started) * 1000, 3),
            outcome=outcome,
            term_count=len(terms),
            error_type=None if error is None else type(error).__name__,
        )


class StaticQueryExpander(QueryExpander):
    """Fixed expansions keyed by the exact query; used for reproducible runs."""

    def __init__(self, expansions: Mapping[str, str]) -> None:
        self._expansions = dict(expansions)

    async def expand(self, query: str) -> tuple[str, ...]:
        text = self._expansions.get(query)
        return () if text is None else parse_expansion(text)


class CachedQueryExpander(QueryExpander):
    """Bounded in-memory cache in front of another expander.

    Expansion costs one LLM call and is stable for the same query, so a small
    bounded cache removes most repeated calls without unbounded growth.
    """

    def __init__(self, inner: QueryExpander, *, max_entries: int = 256) -> None:
        if max_entries <= 0:
            raise ValueError("max_entries must be positive")
        self._inner = inner
        self._max_entries = max_entries
        self._cache: OrderedDict[str, tuple[str, ...]] = OrderedDict()

    async def expand(self, query: str) -> tuple[str, ...]:
        key = " ".join(query.casefold().split())
        cached = self._cache.get(key)
        if cached is not None:
            self._cache.move_to_end(key)
            return cached
        terms = await self._inner.expand(query)
        self._cache[key] = terms
        if len(self._cache) > self._max_entries:
            self._cache.popitem(last=False)
        return terms


__all__ = [
    "CachedQueryExpander",
    "EXPANSION_PROMPT",
    "LiteLLMQueryExpander",
    "QueryExpander",
    "StaticQueryExpander",
    "parse_expansion",
]
