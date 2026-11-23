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
from smeshariki_ai.rag.lore.models import LoreHit

SYSTEM_PROMPT = (
    "Отвечай на вопрос только по переданным фрагментам. Не используй внешние "
    "знания и не придумывай факты. Если во фрагментах нет ответа, ответь ровно: "
    "«В документах нет этой информации». Указывай источник в квадратных "
    "скобках, например [d01]."
)


class LiteLLMAnswerer:
    """Benchmark adapter; not used by the production agent runtime."""

    def __init__(self, provider: LLMProvider) -> None:
        self._provider = provider

    async def answer(
        self,
        question: BenchmarkQuestion,
        hits: Sequence[LoreHit],
    ) -> str:
        context = "\n".join(f"[{hit.document_id}] {hit.text}" for hit in hits)
        messages = (
            Message(role=MessageRole.SYSTEM, content=SYSTEM_PROMPT),
            Message(
                role=MessageRole.USER,
                content=f"Вопрос: {question.text}\n\nФрагменты:\n{context}",
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
