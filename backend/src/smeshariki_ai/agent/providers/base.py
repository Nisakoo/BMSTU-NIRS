from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Sequence

from smeshariki_ai.agent.errors import AgentError
from smeshariki_ai.agent.models import (
    LLMResponse,
    LLMTextDelta,
    Message,
    ToolDefinition,
)

LLMStreamEvent = LLMTextDelta | LLMResponse


class LLMProviderError(AgentError):
    """Raised when an LLM provider request or response cannot be processed."""


class LLMProvider(ABC):
    @abstractmethod
    def stream(
        self,
        messages: Sequence[Message],
        tools: Sequence[ToolDefinition],
    ) -> AsyncIterator[LLMStreamEvent]:
        """Yield text deltas followed by one terminal model response."""


class FakeLLMProvider(LLMProvider):
    async def stream(
        self,
        messages: Sequence[Message],
        tools: Sequence[ToolDefinition],
    ) -> AsyncIterator[LLMStreamEvent]:
        yield LLMResponse(content="")
