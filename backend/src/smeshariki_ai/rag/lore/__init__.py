"""BM25 search over unstructured lore, independent of the agent and HTTP."""

from smeshariki_ai.rag.lore.analyzer import MorphAnalyzer, SimpleAnalyzer, TextAnalyzer
from smeshariki_ai.rag.lore.bm25 import Bm25Params
from smeshariki_ai.rag.lore.chunking import ChunkingConfig, chunk_text
from smeshariki_ai.rag.lore.context import (
    LoreContext,
    LoreContextBuilder,
    LorePassage,
)
from smeshariki_ai.rag.lore.index import InMemoryBm25Index
from smeshariki_ai.rag.lore.models import (
    LoreChunk,
    LoreDocument,
    LoreEntry,
    LoreHit,
    LoreLoadSummary,
    LoreQuery,
    LoreSearchResult,
)
from smeshariki_ai.rag.lore.ports import (
    LoreDataInvalidError,
    LoreDocumentSource,
    LoreIndex,
    LoreSchemaNotReadyError,
    LoreStore,
    LoreStoreError,
    LoreStoreUnavailableError,
)
from smeshariki_ai.rag.lore.services import (
    LoadLore,
    LoreConfig,
    LoreLoadReport,
    SearchLore,
)

__all__ = [
    "Bm25Params",
    "ChunkingConfig",
    "InMemoryBm25Index",
    "LoadLore",
    "LoreChunk",
    "LoreConfig",
    "LoreContext",
    "LoreContextBuilder",
    "LoreDataInvalidError",
    "LoreDocument",
    "LoreDocumentSource",
    "LoreEntry",
    "LoreHit",
    "LoreIndex",
    "LoreLoadReport",
    "LoreLoadSummary",
    "LorePassage",
    "LoreQuery",
    "LoreSchemaNotReadyError",
    "LoreSearchResult",
    "LoreStore",
    "LoreStoreError",
    "LoreStoreUnavailableError",
    "MorphAnalyzer",
    "SearchLore",
    "SimpleAnalyzer",
    "TextAnalyzer",
    "chunk_text",
]
