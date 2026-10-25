from fastapi import FastAPI

from smeshariki_ai.admin import AdminStatsService
from smeshariki_ai.agent import (
    Agent,
    LiteLLMProvider,
    LLMProvider,
    ToolRegistry,
)
from smeshariki_ai.agent.get_context import GetContextTool
from smeshariki_ai.api import create_app
from smeshariki_ai.application import AgentService, InMemoryDialogEventBroker
from smeshariki_ai.auth import AuthService
from smeshariki_ai.cache import RedisAttemptLimiter, RedisTokenBlacklist, create_redis
from smeshariki_ai.config import Config
from smeshariki_ai.db import (
    PostgresAdminStatsStore,
    PostgresHistoryStore,
    PostgresRefreshSessionStore,
    PostgresUserStore,
    create_engine,
)
from smeshariki_ai.dialogs import HistoryStore, InMemoryHistoryStore
from smeshariki_ai.observability import configure_logging
from smeshariki_ai.rag.lookup import KnowledgeLookup
from smeshariki_ai.rag.memory import InMemoryKnowledgeStore
from smeshariki_ai.rag.ports import KnowledgeReader
from smeshariki_ai.rag.postgres import PostgresKnowledgeStore
from smeshariki_ai.rag.tools import LookupKnowledgeTool


def build_agent_service(
    config: Config,
    *,
    llm_provider: LLMProvider | None = None,
    history_store: HistoryStore | None = None,
    knowledge_reader: KnowledgeReader | None = None,
) -> AgentService:
    provider = LiteLLMProvider(config.llm) if llm_provider is None else llm_provider
    knowledge = KnowledgeLookup(knowledge_reader or InMemoryKnowledgeStore())
    tool_registry = ToolRegistry((GetContextTool(), LookupKnowledgeTool(knowledge)))
    agent = Agent(
        llm_provider=provider,
        tool_registry=tool_registry,
        config=config.agent,
    )
    event_broker = InMemoryDialogEventBroker()
    return AgentService(
        agent=agent,
        history_store=history_store or InMemoryHistoryStore(),
        event_broker=event_broker,
    )


def create_application(
    config: Config,
    *,
    llm_provider: LLMProvider | None = None,
    auth_service: AuthService | None = None,
) -> FastAPI:
    configure_logging(config.logging)
    on_shutdown = []
    admin_stats = None
    history_store: HistoryStore | None = None
    knowledge_reader: KnowledgeReader | None = None
    if auth_service is None:
        # Both clients are lazy: no connection is opened until the first request.
        engine = create_engine(config.database)
        redis = create_redis(config.redis)
        history_store = PostgresHistoryStore(engine)
        knowledge_reader = PostgresKnowledgeStore(engine)
        auth_service = AuthService(
            users=PostgresUserStore(engine),
            sessions=PostgresRefreshSessionStore(engine),
            blacklist=RedisTokenBlacklist(redis),
            limiter=RedisAttemptLimiter(redis),
            config=config.auth,
        )
        admin_stats = AdminStatsService(PostgresAdminStatsStore(engine))
        on_shutdown = [engine.dispose, redis.aclose]
    agent_service = build_agent_service(
        config,
        llm_provider=llm_provider,
        history_store=history_store,
        knowledge_reader=knowledge_reader,
    )
    return create_app(
        agent_service,
        auth_service=auth_service,
        auth_cookie_secure=config.auth.cookie_secure,
        admin_stats=admin_stats,
        on_shutdown=on_shutdown,
    )
