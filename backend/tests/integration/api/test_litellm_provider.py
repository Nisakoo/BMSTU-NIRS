import asyncio
import logging
from uuid import UUID

import httpx
import pytest

import smeshariki_ai.agent.providers.litellm as provider_module
from smeshariki_ai.agent import (
    Agent,
    AgentConfig,
    LiteLLMProvider,
    LiteLLMProviderConfig,
    ToolRegistry,
)
from smeshariki_ai.api import create_app
from smeshariki_ai.application import AgentService
from smeshariki_ai.dialogs import InMemoryHistoryStore


@pytest.mark.asyncio
async def test_background_litellm_failure_keeps_accepted_history_unchanged(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="smeshariki_ai")
    request_started = asyncio.Event()
    release_request = asyncio.Event()

    async def failing_completion(**kwargs: object) -> None:
        request_started.set()
        await release_request.wait()
        raise RuntimeError("private upstream response")

    monkeypatch.setattr(
        provider_module.litellm_sdk,
        "acompletion",
        failing_completion,
    )
    provider = LiteLLMProvider(
        LiteLLMProviderConfig(
            model="test/model",
            api_key="private-api-key",
        )
    )
    agent = Agent(
        llm_provider=provider,
        tool_registry=ToolRegistry(()),
        config=AgentConfig(system_prompt="private system prompt"),
    )
    store = InMemoryHistoryStore()
    service = AgentService(agent, store)
    app = create_app(service)
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://test",
    ) as client:
        create_response = await client.post("/api/v1/dialogs")
        dialog_id = UUID(create_response.json()["dialog_id"])
        message_response = await asyncio.wait_for(
            client.post(
                f"/api/v1/dialogs/{dialog_id}/messages",
                json={"request": "private user request"},
            ),
            timeout=0.1,
        )
        await asyncio.wait_for(request_started.wait(), timeout=0.1)

        assert message_response.status_code == 202
        assert message_response.content == b""
        assert await store.get(dialog_id) == ()

        release_request.set()

        async def wait_for_failure() -> None:
            while not any(
                record.getMessage().startswith("dialog.run.failed ")
                for record in caplog.records
            ):
                await asyncio.sleep(0)

        await asyncio.wait_for(wait_for_failure(), timeout=1)

    assert await store.get(dialog_id) == ()
    assert any(
        record.getMessage().startswith("llm.request.failed ")
        and record.error_type == "RuntimeError"
        for record in caplog.records
    )
    assert any(
        record.getMessage().startswith("dialog.run.failed ")
        and record.error_type == "LLMProviderError"
        for record in caplog.records
    )
    assert all(
        private_value not in caplog.text
        for private_value in (
            "private-api-key",
            "private system prompt",
            "private user request",
            "private upstream response",
        )
    )
    await service.shutdown()
