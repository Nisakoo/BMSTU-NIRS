import asyncio
import json
import logging
from collections.abc import AsyncIterator, Iterable
from unittest.mock import AsyncMock

import pytest
from litellm.types.utils import ModelResponse, ModelResponseStream

import smeshariki_ai.agent.providers.litellm as provider_module
from smeshariki_ai.agent.models import (
    LLMResponse,
    LLMTextDelta,
    Message,
    MessageRole,
    ToolCall,
    ToolDefinition,
    ToolError,
    ToolResult,
)
from smeshariki_ai.agent.providers import (
    LiteLLMProvider,
    LiteLLMProviderConfig,
    LLMProviderError,
)


class AsyncChunkStream:
    def __init__(self, chunks: Iterable[object]) -> None:
        self._chunks = tuple(chunks)

    async def __aiter__(self) -> AsyncIterator[object]:
        for chunk in self._chunks:
            await asyncio.sleep(0)
            yield chunk


def make_chunk(
    content: str | None = "answer",
    *,
    tool_calls: list[dict[str, object]] | None = None,
) -> ModelResponseStream:
    return ModelResponseStream(
        choices=[
            {
                "delta": {
                    "content": content,
                    "tool_calls": tool_calls,
                }
            }
        ]
    )


def make_response(
    content: str | None = "answer",
    *,
    tool_calls: list[dict[str, object]] | None = None,
) -> AsyncChunkStream:
    return AsyncChunkStream([make_chunk(content, tool_calls=tool_calls)])


@pytest.mark.asyncio
async def test_generate_awaits_acompletion_with_provider_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    completion = AsyncMock(return_value=make_response())
    monkeypatch.setattr(provider_module.litellm_sdk, "acompletion", completion)
    provider = LiteLLMProvider(
        LiteLLMProviderConfig(
            model="openai/test-model",
            api_key="private-api-key",
            base_url="https://llm.example.test/v1",
            timeout_seconds=12.5,
            num_retries=2,
        )
    )

    await provider.generate(
        (Message(role=MessageRole.USER, content="question"),),
        (),
    )

    completion.assert_awaited_once_with(
        model="openai/test-model",
        messages=[{"role": "user", "content": "question"}],
        stream=True,
        timeout=12.5,
        num_retries=2,
        api_key="private-api-key",
        base_url="https://llm.example.test/v1",
    )


@pytest.mark.asyncio
async def test_generate_maps_text_messages_and_function_definitions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    completion = AsyncMock(return_value=make_response())
    monkeypatch.setattr(provider_module.litellm_sdk, "acompletion", completion)
    provider = LiteLLMProvider(LiteLLMProviderConfig(model="test/model"))
    messages = (
        Message(role=MessageRole.SYSTEM, content="system"),
        Message(role=MessageRole.USER, content="question"),
        Message(role=MessageRole.ASSISTANT, content="previous answer"),
    )
    tools = (
        ToolDefinition(
            name="search_knowledge",
            description="Search the knowledge base.",
            parameters={
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        ),
    )

    await provider.generate(messages, tools)

    kwargs = completion.await_args.kwargs
    assert kwargs["messages"] == [
        {"role": "system", "content": "system"},
        {"role": "user", "content": "question"},
        {"role": "assistant", "content": "previous answer"},
    ]
    assert kwargs["tools"] == [
        {
            "type": "function",
            "function": {
                "name": "search_knowledge",
                "description": "Search the knowledge base.",
                "parameters": {
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                    "required": ["query"],
                },
            },
        }
    ]
    assert messages[0].content == "system"
    assert tools[0].parameters["required"] == ["query"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "tool_result",
    [
        ToolResult(
            call_id="call-1",
            name="search_knowledge",
            output={"matches": ["result"]},
        ),
        ToolResult(
            call_id="call-1",
            name="search_knowledge",
            error=ToolError(code="tool_failed", message="Tool failed safely."),
        ),
    ],
    ids=["success", "safe-error"],
)
async def test_generate_maps_tool_call_and_linked_result(
    monkeypatch: pytest.MonkeyPatch,
    tool_result: ToolResult,
) -> None:
    completion = AsyncMock(return_value=make_response())
    monkeypatch.setattr(provider_module.litellm_sdk, "acompletion", completion)
    provider = LiteLLMProvider(LiteLLMProviderConfig(model="test/model"))
    tool_call = ToolCall(
        id="call-1",
        name="search_knowledge",
        arguments={"query": "Крош"},
    )

    await provider.generate(
        (
            Message(role=MessageRole.ASSISTANT, tool_call=tool_call),
            Message(
                role=MessageRole.TOOL,
                tool_call_id="call-1",
                tool_name="search_knowledge",
                tool_result=tool_result,
            ),
        ),
        (),
    )

    sent_messages = completion.await_args.kwargs["messages"]
    assert sent_messages[0] == {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": "call-1",
                "type": "function",
                "function": {
                    "name": "search_knowledge",
                    "arguments": '{"query":"Крош"}',
                },
            }
        ],
    }
    assert sent_messages[1]["role"] == "tool"
    assert sent_messages[1]["tool_call_id"] == "call-1"
    assert sent_messages[1]["name"] == "search_knowledge"
    assert json.loads(sent_messages[1]["content"]) == tool_result.model_dump(
        mode="json"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("content", "expected"),
    [("answer", "answer"), ("", ""), (None, "")],
)
async def test_generate_preserves_response_content(
    monkeypatch: pytest.MonkeyPatch,
    content: str | None,
    expected: str,
) -> None:
    monkeypatch.setattr(
        provider_module.litellm_sdk,
        "acompletion",
        AsyncMock(return_value=make_response(content)),
    )
    provider = LiteLLMProvider(LiteLLMProviderConfig(model="test/model"))

    response = await provider.generate((), ())

    assert response == LLMResponse(content=expected)


@pytest.mark.asyncio
async def test_generate_rejects_mixed_content_and_tool_calls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    external_tool_calls = [
        {
            "id": "call-1",
            "type": "function",
            "function": {"name": "first", "arguments": '{"value":1}'},
        },
        {
            "id": "call-2",
            "type": "function",
            "function": {"name": "second", "arguments": '{"value":2}'},
        },
    ]
    monkeypatch.setattr(
        provider_module.litellm_sdk,
        "acompletion",
        AsyncMock(
            return_value=make_response("mixed content", tool_calls=external_tool_calls)
        ),
    )
    provider = LiteLLMProvider(LiteLLMProviderConfig(model="test/model"))

    with pytest.raises(LLMProviderError, match="invalid response"):
        await provider.generate((), ())


@pytest.mark.asyncio
async def test_stream_yields_text_chunks_before_terminal_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stream = AsyncChunkStream([make_chunk("first"), make_chunk(" second")])
    monkeypatch.setattr(
        provider_module.litellm_sdk,
        "acompletion",
        AsyncMock(return_value=stream),
    )
    provider = LiteLLMProvider(LiteLLMProviderConfig(model="test/model"))

    events = provider.stream((), ())

    assert await anext(events) == LLMTextDelta(content="first")
    assert await anext(events) == LLMTextDelta(content=" second")
    assert await anext(events) == LLMResponse(content="first second")
    with pytest.raises(StopAsyncIteration):
        await anext(events)


@pytest.mark.asyncio
async def test_stream_assembles_fragmented_tool_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stream = AsyncChunkStream(
        [
            make_chunk(
                None,
                tool_calls=[
                    {
                        "index": 0,
                        "id": "call-",
                        "function": {"name": "search_", "arguments": '{"q"'},
                    }
                ],
            ),
            make_chunk(
                None,
                tool_calls=[
                    {
                        "index": 0,
                        "id": "1",
                        "function": {"name": "knowledge", "arguments": ':"Крош"}'},
                    }
                ],
            ),
        ]
    )
    monkeypatch.setattr(
        provider_module.litellm_sdk,
        "acompletion",
        AsyncMock(return_value=stream),
    )
    provider = LiteLLMProvider(LiteLLMProviderConfig(model="test/model"))

    events = [event async for event in provider.stream((), ())]

    assert events == [
        LLMResponse(
            tool_calls=(
                ToolCall(
                    id="call-1",
                    name="search_knowledge",
                    arguments={"q": "Крош"},
                ),
            )
        )
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "external_response",
    [
        ModelResponse(choices=[]),
        make_response(
            None,
            tool_calls=[
                {
                    "id": "call-1",
                    "type": "function",
                    "function": {"name": "tool", "arguments": "not-json"},
                }
            ],
        ),
        make_response(
            None,
            tool_calls=[
                {
                    "id": "call-1",
                    "type": "function",
                    "function": {"name": "tool", "arguments": "[]"},
                }
            ],
        ),
        object(),
    ],
    ids=["missing-choice", "invalid-json", "arguments-not-object", "wrong-type"],
)
async def test_generate_wraps_malformed_responses(
    monkeypatch: pytest.MonkeyPatch,
    external_response: object,
) -> None:
    monkeypatch.setattr(
        provider_module.litellm_sdk,
        "acompletion",
        AsyncMock(return_value=external_response),
    )
    provider = LiteLLMProvider(LiteLLMProviderConfig(model="test/model"))

    with pytest.raises(LLMProviderError, match="invalid response") as captured:
        await provider.generate((), ())

    assert "not-json" not in str(captured.value)


@pytest.mark.asyncio
async def test_generate_wraps_unserializable_tool_result_without_calling_litellm(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    completion = AsyncMock(return_value=make_response())
    monkeypatch.setattr(provider_module.litellm_sdk, "acompletion", completion)
    provider = LiteLLMProvider(LiteLLMProviderConfig(model="test/model"))
    private_output = object()
    message = Message(
        role=MessageRole.TOOL,
        tool_call_id="call-1",
        tool_name="tool",
        tool_result=ToolResult(
            call_id="call-1",
            name="tool",
            output=private_output,
        ),
    )

    with pytest.raises(LLMProviderError, match="invalid message") as captured:
        await provider.generate((message,), ())

    completion.assert_not_awaited()
    assert repr(private_output) not in str(captured.value)


@pytest.mark.asyncio
async def test_generate_wraps_provider_error_and_logs_only_safe_metadata(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="smeshariki_ai.agent.providers.litellm")
    completion = AsyncMock(side_effect=RuntimeError("private upstream body"))
    monkeypatch.setattr(provider_module.litellm_sdk, "acompletion", completion)
    provider = LiteLLMProvider(
        LiteLLMProviderConfig(
            model="test/model",
            api_key="private-api-key",
            base_url="https://private.example.test/v1",
        )
    )

    with pytest.raises(LLMProviderError, match="request failed") as captured:
        await provider.generate(
            (Message(role=MessageRole.USER, content="private prompt"),),
            (
                ToolDefinition(
                    name="private_tool",
                    description="private description",
                    parameters={"private": "schema"},
                ),
            ),
        )

    assert isinstance(captured.value.__cause__, RuntimeError)
    events = [record.getMessage().split()[0] for record in caplog.records]
    assert events == ["llm.request.started", "llm.request.failed"]
    assert caplog.records[0].model == "test/model"
    assert caplog.records[0].message_count == 1
    assert caplog.records[0].tool_count == 1
    assert caplog.records[1].error_type == "RuntimeError"
    assert all(
        private_value not in caplog.text
        for private_value in (
            "private-api-key",
            "private.example.test",
            "private prompt",
            "private_tool",
            "private description",
            "private upstream body",
        )
    )


@pytest.mark.asyncio
async def test_generate_propagates_cancellation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        provider_module.litellm_sdk,
        "acompletion",
        AsyncMock(side_effect=asyncio.CancelledError),
    )
    provider = LiteLLMProvider(LiteLLMProviderConfig(model="test/model"))

    with pytest.raises(asyncio.CancelledError):
        await provider.generate((), ())


@pytest.mark.asyncio
async def test_one_provider_allows_independent_calls_to_progress_concurrently(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first_started = asyncio.Event()
    release_first = asyncio.Event()
    calls: list[str] = []

    async def controlled_completion(**kwargs: object) -> ModelResponse:
        content = kwargs["messages"][0]["content"]  # type: ignore[index]
        assert isinstance(content, str)
        calls.append(content)
        if content == "first":
            first_started.set()
            await release_first.wait()
        return make_response(f"answer:{content}")

    monkeypatch.setattr(
        provider_module.litellm_sdk,
        "acompletion",
        controlled_completion,
    )
    provider = LiteLLMProvider(LiteLLMProviderConfig(model="test/model"))

    first_task = asyncio.create_task(
        provider.generate((Message(role=MessageRole.USER, content="first"),), ())
    )
    await asyncio.wait_for(first_started.wait(), timeout=0.1)
    second_response = await asyncio.wait_for(
        provider.generate((Message(role=MessageRole.USER, content="second"),), ()),
        timeout=0.1,
    )

    assert second_response.content == "answer:second"
    assert not first_task.done()
    assert calls == ["first", "second"]

    release_first.set()
    first_response = await asyncio.wait_for(first_task, timeout=0.1)
    assert first_response.content == "answer:first"
