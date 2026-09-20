import logging

from fastapi import FastAPI

from smeshariki_ai.agent import (
    Agent,
    LiteLLMProvider,
    LLMProvider,
    ToolRegistry,
)
from smeshariki_ai.api import create_app
from smeshariki_ai.application import AgentService, InMemoryDialogEventBroker
from smeshariki_ai.config import Config
from smeshariki_ai.dialogs import InMemoryHistoryStore


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    logging.getLogger("smeshariki_ai").setLevel(logging.INFO)


def build_agent_service(
    config: Config,
    *,
    llm_provider: LLMProvider | None = None,
) -> AgentService:
    provider = LiteLLMProvider(config.llm) if llm_provider is None else llm_provider
    tool_registry = ToolRegistry(())
    agent = Agent(
        llm_provider=provider,
        tool_registry=tool_registry,
        config=config.agent,
    )
    history_store = InMemoryHistoryStore()
    event_broker = InMemoryDialogEventBroker()
    return AgentService(
        agent=agent,
        history_store=history_store,
        event_broker=event_broker,
    )


def create_application(
    config: Config,
    *,
    llm_provider: LLMProvider | None = None,
) -> FastAPI:
    configure_logging()
    agent_service = build_agent_service(
        config,
        llm_provider=llm_provider,
    )
    return create_app(agent_service)
