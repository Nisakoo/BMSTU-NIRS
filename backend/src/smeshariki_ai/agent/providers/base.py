from abc import ABC, abstractmethod
from collections.abc import Sequence

from smeshariki_ai.agent.errors import AgentError
from smeshariki_ai.agent.models import LLMResponse, Message, ToolDefinition


class LLMProviderError(AgentError):
    """Raised when an LLM provider request or response cannot be processed."""


class LLMProvider(ABC):
    @abstractmethod
    async def generate(
        self,
        messages: Sequence[Message],
        tools: Sequence[ToolDefinition],
    ) -> LLMResponse:
        """Return the next model response for the current agent context."""


class FakeLLMProvider(LLMProvider):
    async def generate(
        self,
        messages: Sequence[Message],
        tools: Sequence[ToolDefinition],
    ) -> LLMResponse:
        return LLMResponse(content="")
