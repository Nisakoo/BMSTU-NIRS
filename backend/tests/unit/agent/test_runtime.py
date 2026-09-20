import logging
from collections.abc import AsyncIterator, Sequence
from typing import ClassVar

import pytest
from pydantic import BaseModel, ConfigDict

from smeshariki_ai.agent.errors import (
    AgentIterationLimitError,
    InvalidLLMResponseError,
)
from smeshariki_ai.agent.models import (
    AgentConfig,
    AgentResponse,
    AgentTextDelta,
    LLMResponse,
    LLMResultType,
    LLMTextDelta,
    Message,
    MessageRole,
    ToolCall,
    ToolDefinition,
    UserRequest,
)
from smeshariki_ai.agent.providers import LLMProvider, LLMStreamEvent
from smeshariki_ai.agent.runtime import Agent
from smeshariki_ai.agent.tools import Tool, ToolRegistry


class ScriptedLLMProvider(LLMProvider):
    def __init__(
        self,
        responses: Sequence[LLMResponse | Sequence[LLMStreamEvent]],
    ) -> None:
        self._responses = tuple(
            (
                (
                    *(
                        (LLMTextDelta(content=response.content),)
                        if response.content
                        else ()
                    ),
                    response,
                )
                if isinstance(response, LLMResponse)
                else tuple(response)
            )
            for response in responses
        )
        self.calls: list[tuple[tuple[Message, ...], tuple[ToolDefinition, ...]]] = []

    async def stream(
        self,
        messages: Sequence[Message],
        tools: Sequence[ToolDefinition],
    ) -> AsyncIterator[LLMStreamEvent]:
        self.calls.append((tuple(messages), tuple(tools)))
        for event in self._responses[len(self.calls) - 1]:
            yield event


class EchoArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str


class RecordingTool(Tool):
    name: ClassVar[str] = "echo"
    description: ClassVar[str] = "Return the supplied text."
    arguments_model: ClassVar[type[BaseModel]] = EchoArguments

    def __init__(self) -> None:
        self.calls: list[EchoArguments] = []

    async def execute(self, arguments: BaseModel) -> object:
        assert isinstance(arguments, EchoArguments)
        self.calls.append(arguments)
        return {"echo": arguments.text}


class FailingTool(Tool):
    name: ClassVar[str] = "failing"
    description: ClassVar[str] = "Always fails."
    arguments_model: ClassVar[type[BaseModel]] = EchoArguments

    async def execute(self, arguments: BaseModel) -> object:
        raise RuntimeError("private failure detail")


def make_agent(
    provider: LLMProvider,
    tools: Sequence[Tool] = (),
    *,
    max_iterations: int = 4,
) -> Agent:
    return Agent(
        llm_provider=provider,
        tool_registry=ToolRegistry(tools),
        config=AgentConfig(
            system_prompt="You are a Smeshariki expert.",
            max_iterations=max_iterations,
        ),
    )


async def collect_agent_events(
    agent: Agent,
    history: Sequence[Message],
    request: UserRequest,
) -> list[AgentTextDelta | AgentResponse]:
    return [event async for event in agent.run(history, request)]


@pytest.mark.parametrize(
    ("response", "expected_type"),
    [
        (LLMResponse(content=""), LLMResultType.FINAL),
        (
            LLMResponse(tool_calls=(ToolCall(id="call-1", name="echo", arguments={}),)),
            LLMResultType.TOOL_CALL,
        ),
        (LLMResponse(), LLMResultType.INVALID),
    ],
)
def test_llm_response_classification_uses_explicit_status(
    response: LLMResponse,
    expected_type: LLMResultType,
) -> None:
    assert Agent._result_type(response) is expected_type


@pytest.mark.asyncio
async def test_direct_empty_response_preserves_history_and_builds_context() -> None:
    provider = ScriptedLLMProvider([LLMResponse(content="")])
    history = (
        Message(role=MessageRole.USER, content="Earlier question"),
        Message(role=MessageRole.ASSISTANT, content="Earlier answer"),
    )
    original_history = tuple(history)
    tool = RecordingTool()

    events = await collect_agent_events(
        make_agent(provider, [tool]),
        history,
        UserRequest(content="Current question"),
    )

    assert events == [AgentResponse(content="")]
    assert history == original_history
    messages, definitions = provider.calls[0]
    assert [(message.role, message.content) for message in messages] == [
        (MessageRole.SYSTEM, "You are a Smeshariki expert."),
        (MessageRole.USER, "Earlier question"),
        (MessageRole.ASSISTANT, "Earlier answer"),
        (MessageRole.USER, "Current question"),
    ]
    assert [definition.name for definition in definitions] == ["echo"]


@pytest.mark.asyncio
async def test_run_yields_final_text_incrementally() -> None:
    script = [
        LLMTextDelta(content="Привет"),
        LLMTextDelta(content=", Крош!"),
        LLMResponse(content="Привет, Крош!"),
    ]
    streaming_provider = ScriptedLLMProvider([script])

    events = [
        event
        async for event in make_agent(streaming_provider).run(
            (), UserRequest(content="question")
        )
    ]

    assert events == [
        AgentTextDelta(content="Привет"),
        AgentTextDelta(content=", Крош!"),
        AgentResponse(content="Привет, Крош!"),
    ]


@pytest.mark.asyncio
async def test_run_hides_tool_iteration_and_yields_only_final_text() -> None:
    tool_call = ToolCall(id="call-1", name="echo", arguments={"text": "hello"})
    provider = ScriptedLLMProvider(
        [
            [LLMResponse(tool_calls=(tool_call,))],
            [
                LLMTextDelta(content="do"),
                LLMTextDelta(content="ne"),
                LLMResponse(content="done"),
            ],
        ]
    )

    events = [
        event
        async for event in make_agent(provider, [RecordingTool()]).run(
            (), UserRequest(content="Use a tool")
        )
    ]

    assert events == [
        AgentTextDelta(content="do"),
        AgentTextDelta(content="ne"),
        AgentResponse(content="done"),
    ]


@pytest.mark.asyncio
async def test_run_rejects_terminal_text_that_differs_from_deltas() -> None:
    provider = ScriptedLLMProvider(
        [[LLMTextDelta(content="partial"), LLMResponse(content="different")]]
    )

    stream = make_agent(provider).run((), UserRequest(content="question"))
    assert await anext(stream) == AgentTextDelta(content="partial")
    with pytest.raises(InvalidLLMResponseError):
        await anext(stream)


@pytest.mark.asyncio
async def test_tool_call_is_added_with_structured_result_before_final_response() -> (
    None
):
    tool_call = ToolCall(id="call-1", name="echo", arguments={"text": "hello"})
    provider = ScriptedLLMProvider(
        [
            LLMResponse(tool_calls=(tool_call,)),
            LLMResponse(content="done"),
        ]
    )
    tool = RecordingTool()

    events = await collect_agent_events(
        make_agent(provider, [tool]), (), UserRequest(content="Use a tool")
    )

    assert events[-1] == AgentResponse(content="done")
    assert tool.calls == [EchoArguments(text="hello")]
    second_context, _ = provider.calls[1]
    assert second_context[-2].role is MessageRole.ASSISTANT
    assert second_context[-2].tool_call == tool_call
    assert second_context[-1].role is MessageRole.TOOL
    assert second_context[-1].tool_result is not None
    assert second_context[-1].tool_result.output == {"echo": "hello"}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response",
    [
        LLMResponse(
            content="ambiguous",
            tool_calls=(ToolCall(id="call-1", name="echo", arguments={}),),
        ),
        LLMResponse(
            tool_calls=(
                ToolCall(id="call-1", name="echo", arguments={}),
                ToolCall(id="call-2", name="echo", arguments={}),
            )
        ),
        LLMResponse(),
    ],
    ids=["text-and-tool", "multiple-tools", "empty-shape"],
)
async def test_invalid_llm_response_is_rejected(response: LLMResponse) -> None:
    provider = ScriptedLLMProvider([response])

    with pytest.raises(InvalidLLMResponseError):
        await collect_agent_events(
            make_agent(provider), (), UserRequest(content="question")
        )

    assert len(provider.calls) == 1


@pytest.mark.asyncio
async def test_iteration_limit_stops_before_fifth_llm_call() -> None:
    responses = [
        LLMResponse(
            tool_calls=(ToolCall(id=f"call-{iteration}", name="missing", arguments={}),)
        )
        for iteration in range(4)
    ]
    provider = ScriptedLLMProvider(responses)

    with pytest.raises(AgentIterationLimitError):
        await collect_agent_events(
            make_agent(provider), (), UserRequest(content="question")
        )

    assert len(provider.calls) == 4


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("tool_call", "tools", "expected_code"),
    [
        (
            ToolCall(id="call-1", name="missing", arguments={}),
            (),
            "tool_not_found",
        ),
        (
            ToolCall(id="call-1", name="echo", arguments={"wrong": "value"}),
            (RecordingTool(),),
            "invalid_arguments",
        ),
        (
            ToolCall(id="call-1", name="failing", arguments={"text": "value"}),
            (FailingTool(),),
            "tool_execution_failed",
        ),
    ],
)
async def test_tool_error_is_returned_to_llm_and_loop_continues(
    tool_call: ToolCall,
    tools: Sequence[Tool],
    expected_code: str,
) -> None:
    provider = ScriptedLLMProvider(
        [LLMResponse(tool_calls=(tool_call,)), LLMResponse(content="recovered")]
    )

    events = await collect_agent_events(
        make_agent(provider, tools), (), UserRequest(content="question")
    )

    assert events[-1] == AgentResponse(content="recovered")
    tool_message = provider.calls[1][0][-1]
    assert tool_message.tool_result is not None
    assert tool_message.tool_result.error is not None
    assert tool_message.tool_result.error.code == expected_code


@pytest.mark.asyncio
async def test_runtime_logs_events_without_context_or_tool_payload(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="smeshariki_ai.agent.runtime")
    tool_call = ToolCall(
        id="call-1",
        name="echo",
        arguments={"text": "private tool argument"},
    )
    provider = ScriptedLLMProvider(
        [LLMResponse(tool_calls=(tool_call,)), LLMResponse(content="private output")]
    )

    await collect_agent_events(
        make_agent(provider, [RecordingTool()]),
        (Message(role=MessageRole.USER, content="private history"),),
        UserRequest(content="private request"),
    )

    events = [record.getMessage().split()[0] for record in caplog.records]
    assert events == [
        "agent.run.started",
        "agent.iteration.started",
        "agent.llm.completed",
        "agent.tool.completed",
        "agent.iteration.started",
        "agent.llm.completed",
        "agent.run.completed",
    ]
    assert "iteration=1 result_type=tool_call" in caplog.records[2].getMessage()
    assert "tool_name=echo tool_status=success" in caplog.records[3].getMessage()
    assert all(
        private_value not in caplog.text
        for private_value in (
            "private history",
            "private request",
            "private tool argument",
            "private output",
        )
    )


@pytest.mark.asyncio
async def test_controlled_failure_is_logged_without_request(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="smeshariki_ai.agent.runtime")
    provider = ScriptedLLMProvider([LLMResponse()])

    with pytest.raises(InvalidLLMResponseError):
        await collect_agent_events(
            make_agent(provider), (), UserRequest(content="private request")
        )

    assert caplog.records[-1].getMessage().startswith("agent.run.failed ")
    assert "error_type=InvalidLLMResponseError" in caplog.records[-1].getMessage()
    assert "private request" not in caplog.text
