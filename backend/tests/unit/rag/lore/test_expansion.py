from __future__ import annotations

from collections.abc import AsyncIterator, Sequence

import pytest

from smeshariki_ai.agent import (
    LLMProvider,
    LLMProviderError,
    LLMResponse,
    LLMTextDelta,
    Message,
)
from smeshariki_ai.rag.lore.expansion import (
    CachedQueryExpander,
    LiteLLMQueryExpander,
    QueryExpander,
    StaticQueryExpander,
    parse_expansion,
)


class ScriptedProvider(LLMProvider):
    def __init__(self, content: str | None = None, *, error: bool = False) -> None:
        self.content = content
        self.error = error
        self.messages: tuple[Message, ...] = ()

    async def stream(
        self,
        messages: Sequence[Message],
        tools: Sequence[object],
    ) -> AsyncIterator[LLMTextDelta | LLMResponse]:
        self.messages = tuple(messages)
        if self.error:
            raise LLMProviderError("boom")
        yield LLMResponse(content=self.content)


def test_parse_expansion_keeps_words_only() -> None:
    text = "1. Футбол, гольф; мяч!\n2. игра — спорт."

    assert parse_expansion(text) == ("футбол", "гольф", "мяч", "игра", "спорт")


def test_parse_expansion_folds_case_and_deduplicates() -> None:
    assert parse_expansion("Мяч мяч МЯЧ клюшка") == ("мяч", "клюшка")


def test_parse_expansion_respects_the_limit() -> None:
    assert parse_expansion("а б в г д", max_terms=3) == ("а", "б", "в")
    assert parse_expansion("а б", max_terms=0) == ()


def test_parse_expansion_returns_nothing_for_prose_without_words() -> None:
    assert parse_expansion("!!! ... ---") == ()


async def test_expander_returns_parsed_terms() -> None:
    provider = ScriptedProvider("футбол гольф мяч игра спорт")
    expander = LiteLLMQueryExpander(provider)

    terms = await expander.expand("В какие игры играют герои?")

    assert terms == ("футбол", "гольф", "мяч", "игра", "спорт")
    assert provider.messages[0].content
    assert "игры" in provider.messages[1].content


async def test_expander_degrades_on_provider_error() -> None:
    expander = LiteLLMQueryExpander(ScriptedProvider(error=True))

    assert await expander.expand("В какие игры играют герои?") == ()


async def test_expander_returns_nothing_for_an_empty_answer() -> None:
    expander = LiteLLMQueryExpander(ScriptedProvider(None))

    assert await expander.expand("Вопрос") == ()


def test_expander_rejects_a_non_positive_limit() -> None:
    with pytest.raises(ValueError):
        LiteLLMQueryExpander(ScriptedProvider("x"), max_terms=0)


async def test_static_expander_uses_the_exact_query() -> None:
    expander = StaticQueryExpander({"В какие игры?": "Футбол, гольф!"})

    assert await expander.expand("В какие игры?") == ("футбол", "гольф")
    assert await expander.expand("Другой вопрос") == ()


class CountingExpander(QueryExpander):
    def __init__(self, terms: tuple[str, ...]) -> None:
        self.calls = 0
        self._terms = terms

    async def expand(self, query: str) -> tuple[str, ...]:
        self.calls += 1
        return self._terms


async def test_cached_expander_calls_the_inner_expander_once() -> None:
    inner = CountingExpander(("мяч",))
    expander = CachedQueryExpander(inner)

    first = await expander.expand("В какие игры играют герои?")
    second = await expander.expand("в какие  ИГРЫ играют герои?")

    assert first == ("мяч",)
    assert second == ("мяч",)
    assert inner.calls == 1


async def test_cached_expander_is_bounded() -> None:
    inner = CountingExpander(("мяч",))
    expander = CachedQueryExpander(inner, max_entries=1)

    await expander.expand("первый")
    await expander.expand("второй")
    await expander.expand("первый")

    assert inner.calls == 3


def test_cached_expander_rejects_a_non_positive_size() -> None:
    with pytest.raises(ValueError):
        CachedQueryExpander(CountingExpander(()), max_entries=0)
