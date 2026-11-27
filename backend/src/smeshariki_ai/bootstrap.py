from fastapi import FastAPI

from smeshariki_ai.admin import AdminReportsService, AdminStatsService
from smeshariki_ai.agent import (
    Agent,
    LiteLLMProvider,
    LLMProvider,
    ToolRegistry,
)
from smeshariki_ai.api import create_app
from smeshariki_ai.application import AgentService, InMemoryDialogEventBroker
from smeshariki_ai.auth import AuthService
from smeshariki_ai.cache import RedisAttemptLimiter, RedisTokenBlacklist, create_redis
from smeshariki_ai.config import Config
from smeshariki_ai.db import (
    PostgresAdminStatsStore,
    PostgresHistoryStore,
    PostgresMessageAudioStore,
    PostgresRefreshSessionStore,
    PostgresReportStore,
    PostgresUserStore,
    create_engine,
)
from smeshariki_ai.dialogs import HistoryStore, InMemoryHistoryStore
from smeshariki_ai.observability import configure_logging
from smeshariki_ai.rag.lookup import KnowledgeLookup
from smeshariki_ai.rag.lore.analyzer import MorphAnalyzer, SimpleAnalyzer, TextAnalyzer
from smeshariki_ai.rag.lore.context import LoreContextBuilder
from smeshariki_ai.rag.lore.expansion import CachedQueryExpander, LiteLLMQueryExpander
from smeshariki_ai.rag.lore.hybrid import DenseSearcher
from smeshariki_ai.rag.lore.index import InMemoryBm25Index
from smeshariki_ai.rag.lore.ports import LoreIndex
from smeshariki_ai.rag.lore.postgres import PostgresBm25Index
from smeshariki_ai.rag.lore.rerank import LLMReranker
from smeshariki_ai.rag.lore.services import SearchLore
from smeshariki_ai.rag.lore.tools import SearchLoreTool
from smeshariki_ai.rag.memory import InMemoryKnowledgeStore
from smeshariki_ai.rag.ports import KnowledgeReader
from smeshariki_ai.rag.postgres import PostgresKnowledgeStore
from smeshariki_ai.rag.story_canon import StoryCanonLookup
from smeshariki_ai.rag.tools import GetStoryCanonTool, LookupKnowledgeTool
from smeshariki_ai.speech.ceph import CephS3AudioObjectStore
from smeshariki_ai.speech.encoder import AudioEncoder, FfmpegAudioEncoder
from smeshariki_ai.speech.memory import InMemoryMessageAudioStore
from smeshariki_ai.speech.memory_objects import InMemoryAudioObjectStore
from smeshariki_ai.speech.objects import AudioObjectStore
from smeshariki_ai.speech.provider import SpeechProvider
from smeshariki_ai.speech.service import NarratorSpeechService
from smeshariki_ai.speech.silero import SileroSpeechProvider


def build_agent_service(
    config: Config,
    *,
    llm_provider: LLMProvider | None = None,
    history_store: HistoryStore | None = None,
    knowledge_reader: KnowledgeReader | None = None,
    lore_index: LoreIndex | None = None,
    lore_analyzer: TextAnalyzer | None = None,
    lore_dense: DenseSearcher | None = None,
) -> AgentService:
    provider = LiteLLMProvider(config.llm) if llm_provider is None else llm_provider
    reader = knowledge_reader or InMemoryKnowledgeStore()
    knowledge = KnowledgeLookup(reader)
    story_canon = StoryCanonLookup(reader)
    lore = SearchLore(
        lore_index or InMemoryBm25Index(),
        lore_analyzer or SimpleAnalyzer(),
        dense=lore_dense,
        hybrid_weight=config.rag.hybrid_bm25_weight,
    )
    expander = (
        CachedQueryExpander(LiteLLMQueryExpander(provider))
        if config.rag.query_expansion_enabled
        else None
    )
    lore_context = LoreContextBuilder(
        retrieval_k=config.rag.lore_retrieval_k,
        max_passages=config.rag.lore_max_passages,
        max_chars=config.rag.lore_max_chars,
        min_score=config.rag.lore_min_score,
    )
    ranker = LLMReranker(provider) if config.rag.lore_rerank_enabled else None
    tool_registry = ToolRegistry(
        (
            LookupKnowledgeTool(knowledge),
            GetStoryCanonTool(story_canon),
            SearchLoreTool(
                lore,
                lore_context,
                expander,
                config.rag.query_expansion_mode,
                ranker,
            ),
        )
    )
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
    speech_provider: SpeechProvider | None = None,
    speech_encoder: AudioEncoder | None = None,
    speech_object_store: AudioObjectStore | None = None,
) -> FastAPI:
    configure_logging(config.logging)
    on_shutdown = []
    admin_stats = None
    admin_reports = None
    audio_store = None
    knowledge_reader: KnowledgeReader | None = None
    lore_index: LoreIndex | None = None
    lore_analyzer: TextAnalyzer | None = None
    lore_dense: DenseSearcher | None = None
    if auth_service is None:
        # Both clients are lazy: no connection is opened until the first request.
        engine = create_engine(config.database)
        redis = create_redis(config.redis)
        history_store: HistoryStore = PostgresHistoryStore(engine)
        audio_store = PostgresMessageAudioStore(engine)
        knowledge_reader = PostgresKnowledgeStore(engine)
        lore_index = PostgresBm25Index(engine)
        lore_analyzer = MorphAnalyzer()
        if config.rag.hybrid_enabled:
            from smeshariki_ai.rag.lore.embeddings import LocalEmbeddingProvider
            from smeshariki_ai.rag.lore.postgres import PostgresDenseIndex

            lore_dense = PostgresDenseIndex(engine, LocalEmbeddingProvider())
        auth_service = AuthService(
            users=PostgresUserStore(engine),
            sessions=PostgresRefreshSessionStore(engine),
            blacklist=RedisTokenBlacklist(redis),
            limiter=RedisAttemptLimiter(redis),
            config=config.auth,
        )
        admin_stats = AdminStatsService(PostgresAdminStatsStore(engine))
        admin_reports = AdminReportsService(PostgresReportStore(engine))
        on_shutdown = [engine.dispose, redis.aclose]
    else:
        history_store = InMemoryHistoryStore()
    speech_service = None
    if config.speech.enabled:
        speech_service = NarratorSpeechService(
            history_store=history_store,
            audio_store=audio_store or InMemoryMessageAudioStore(),
            object_store=speech_object_store
            or (
                CephS3AudioObjectStore(config.ceph)
                if audio_store is not None
                else InMemoryAudioObjectStore()
            ),
            provider=speech_provider
            or SileroSpeechProvider.from_path(config.speech.model_path),
            encoder=speech_encoder or FfmpegAudioEncoder(),
            config=config.speech,
            object_prefix=config.ceph.prefix,
        )
    agent_service = build_agent_service(
        config,
        llm_provider=llm_provider,
        history_store=history_store,
        knowledge_reader=knowledge_reader,
        lore_index=lore_index,
        lore_analyzer=lore_analyzer,
        lore_dense=lore_dense,
    )
    return create_app(
        agent_service,
        auth_service=auth_service,
        auth_cookie_secure=config.auth.cookie_secure,
        admin_stats=admin_stats,
        admin_reports=admin_reports,
        speech_service=speech_service,
        on_shutdown=on_shutdown,
    )
