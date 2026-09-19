import httpx
import pytest

from smeshariki_ai.agent import Agent, AgentConfig, FakeLLMProvider, ToolRegistry
from smeshariki_ai.api import create_app
from smeshariki_ai.application import AgentService
from smeshariki_ai.dialogs import InMemoryHistoryStore


@pytest.mark.asyncio
async def test_agent_test_returns_self_contained_same_origin_html() -> None:
    agent = Agent(
        llm_provider=FakeLLMProvider(),
        tool_registry=ToolRegistry(()),
        config=AgentConfig(system_prompt="test"),
    )
    service = AgentService(agent, InMemoryHistoryStore())
    app = create_app(service)
    client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    )

    async with client:
        response = await client.get("/agent_test")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert response.text.count("<html") == 1
    assert "EventSource" in response.text
    assert "api/v1/dialogs" in response.text
    assert "message_delta" in response.text
    assert "textContent" in response.text
    assert "localStorage" not in response.text
    assert "http://" not in response.text
    assert "https://" not in response.text
    assert "<script src=" not in response.text
    assert "<link" not in response.text
    await service.shutdown()
