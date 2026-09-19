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
    async def generate(
        self,
        messages: Sequence[Message],
        tools: Sequence[ToolDefinition],
    ) -> LLMResponse:
        """Collect and return the terminal response from a provider stream."""
        response: LLMResponse | None = None
        async for event in self.stream(messages, tools):
            if isinstance(event, LLMResponse):
                if response is not None:
                    raise LLMProviderError(
                        "The LLM provider returned an invalid response."
                    )
                response = event
            elif response is not None:
                raise LLMProviderError("The LLM provider returned an invalid response.")

        if response is None:
            raise LLMProviderError("The LLM provider returned an invalid response.")
        return response

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
