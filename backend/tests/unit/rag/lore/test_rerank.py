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
from smeshariki_ai.rag.lore.models import LoreHit
from smeshariki_ai.rag.lore.rerank import (
    LLMReranker,
    NoopRanker,
    parse_ranking,
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


def hit(document_id: str, score: float = 1.0) -> LoreHit:
    return LoreHit(
        chunk_id=1,
        document_id=document_id,
        position=0,
        title=document_id.upper(),
        text=f"Текст {document_id}",
        score=score,
        rank=1,
    )


def hits(*ids: str) -> tuple[LoreHit, ...]:
    return tuple(hit(document_id) for document_id in ids)


def test_parse_ranking_keeps_valid_numbers_in_order() -> None:
    assert parse_ranking("3, 1, 7", total=5) == (3, 1)


def test_parse_ranking_deduplicates_and_ignores_zero() -> None:
    assert parse_ranking("2 2 0 1", total=3) == (2, 1)


def test_parse_ranking_without_numbers_is_empty() -> None:
    assert parse_ranking("нет подходящих", total=3) == ()
    assert parse_ranking("2, 1", total=0) == ()


async def test_reranker_puts_chosen_passages_first() -> None:
    reranker = LLMReranker(ScriptedProvider("3, 1"))

    result = await reranker.rerank("вопрос", hits("a", "b", "c"), limit=3)

    assert [item.document_id for item in result] == ["c", "a", "b"]


async def test_reranker_keeps_the_candidate_set_when_only_one_is_chosen() -> None:
    reranker = LLMReranker(ScriptedProvider("2"))

    result = await reranker.rerank("вопрос", hits("a", "b", "c"), limit=3)

    assert [item.document_id for item in result] == ["b", "a", "c"]


async def test_reranker_respects_the_limit() -> None:
    reranker = LLMReranker(ScriptedProvider("3"))

    result = await reranker.rerank("вопрос", hits("a", "b", "c", "d"), limit=2)

    assert len(result) == 2
    assert [item.document_id for item in result] == ["c", "a"]


async def test_reranker_falls_back_on_provider_error() -> None:
    reranker = LLMReranker(ScriptedProvider(error=True))

    result = await reranker.rerank("вопрос", hits("a", "b"), limit=2)

    assert [item.document_id for item in result] == ["a", "b"]


async def test_reranker_falls_back_on_unparsable_answer() -> None:
    reranker = LLMReranker(ScriptedProvider("не знаю"))

    result = await reranker.rerank("вопрос", hits("a", "b"), limit=2)

    assert [item.document_id for item in result] == ["a", "b"]


async def test_reranker_is_a_noop_for_a_single_candidate() -> None:
    provider = ScriptedProvider("1")
    reranker = LLMReranker(provider)

    result = await reranker.rerank("вопрос", hits("a"), limit=1)

    assert [item.document_id for item in result] == ["a"]
    assert provider.messages == ()


async def test_noop_ranker_keeps_the_order() -> None:
    result = await NoopRanker().rerank("вопрос", hits("a", "b", "c"), limit=2)

    assert [item.document_id for item in result] == ["a", "b"]


async def test_reranker_prompt_lists_the_fragments() -> None:
    provider = ScriptedProvider("1")
    reranker = LLMReranker(provider)

    await reranker.rerank("вопрос про игры", hits("a", "b"), limit=2)

    prompt = provider.messages[1].content
    assert "вопрос про игры" in prompt
    assert "1. A" in prompt and "2. B" in prompt


def test_reranker_requires_a_provider() -> None:
    with pytest.raises(TypeError):
        LLMReranker()  # type: ignore[call-arg]
