"""LLM adapter of the benchmark: answers only from retrieved lore passages."""

from __future__ import annotations

from collections.abc import Sequence

from smeshariki_ai.agent import (
    LLMProvider,
    LLMProviderError,
    LLMResponse,
    LLMTextDelta,
    Message,
    MessageRole,
)
from smeshariki_ai.rag.lore.benchmark import BenchmarkError, BenchmarkQuestion
from smeshariki_ai.rag.lore.context import LoreContext
from smeshariki_ai.rag.lore.models import LoreHit

SYSTEM_PROMPT = (
    "Ответь на вопрос, используя только переданные фрагменты. Перечисли все "
    "факты из фрагментов, которые относятся к вопросу, даже если они короткие. "
    "Не используй внешние знания и не добавляй того, чего нет в тексте. Если "
    "фрагменты не содержат ответа, ответь ровно: «В документах нет этой "
    "информации»."
)


class LiteLLMAnswerer:
    """Benchmark adapter; not used by the production agent runtime."""

    def __init__(self, provider: LLMProvider) -> None:
        self._provider = provider

    async def answer(
        self,
        question: BenchmarkQuestion,
        hits: Sequence[LoreHit],
        context: LoreContext | None = None,
    ) -> str:
        # The built context is what the agent would read: no chunk ids, at most
        # a few passages. Raw hits stay as a fallback for callers without one.
        if context is not None and context.passages:
            body = "\n".join(
                f"[{passage.title}] {passage.text}" for passage in context.passages
            )
        else:
            body = "\n".join(f"[{hit.document_id}] {hit.text}" for hit in hits)
        messages = (
            Message(role=MessageRole.SYSTEM, content=SYSTEM_PROMPT),
            Message(
                role=MessageRole.USER,
                content=f"Вопрос: {question.text}\n\nФрагменты:\n{body}",
            ),
        )
        response: LLMResponse | None = None
        try:
            async for event in self._provider.stream(messages, ()):
                if isinstance(event, LLMTextDelta):
                    continue
                if isinstance(event, LLMResponse):
                    response = event
        except LLMProviderError as error:
            raise BenchmarkError("answer generation failed") from error
        return "" if response is None or response.content is None else response.content
