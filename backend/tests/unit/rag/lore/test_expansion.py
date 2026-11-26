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
    LiteLLMQueryExpander,
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
