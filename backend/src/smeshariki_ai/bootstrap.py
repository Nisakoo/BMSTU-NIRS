import logging

from fastapi import FastAPI

from smeshariki_ai.agent import (
    Agent,
    AgentConfig,
    FakeLLMProvider,
    ToolRegistry,
)
from smeshariki_ai.api import create_app
from smeshariki_ai.application import AgentService
from smeshariki_ai.config import ApplicationConfig, load_config
from smeshariki_ai.dialogs import InMemoryHistoryStore


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    logging.getLogger("smeshariki_ai").setLevel(logging.INFO)


def build_agent_service(config: ApplicationConfig) -> AgentService:
    llm_provider = FakeLLMProvider()
    tool_registry = ToolRegistry(())
    agent = Agent(
        llm_provider=llm_provider,
        tool_registry=tool_registry,
        config=AgentConfig(
            system_prompt=config.agent_system_prompt,
            max_iterations=config.agent_max_iterations,
        ),
    )
    history_store = InMemoryHistoryStore()
    return AgentService(agent=agent, history_store=history_store)


def create_application(config: ApplicationConfig | None = None) -> FastAPI:
    configure_logging()
    application_config = load_config() if config is None else config
    agent_service = build_agent_service(application_config)
    return create_app(agent_service)
