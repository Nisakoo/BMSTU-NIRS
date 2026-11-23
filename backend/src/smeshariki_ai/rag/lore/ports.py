"""Outbound ports of the BM25 lore search."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable, Sequence

from smeshariki_ai.rag.lore.bm25 import Bm25Params
from smeshariki_ai.rag.lore.models import (
    LoreDocument,
    LoreEntry,
    LoreHit,
    LoreLoadSummary,
)


class LoreStoreError(Exception):
    """Base error of the lore storage."""


class LoreStoreUnavailableError(LoreStoreError):
    """The lore database cannot serve the request."""


class LoreSchemaNotReadyError(LoreStoreError):
    """The ``rag_lore_*`` tables do not exist: migrations are missing."""


class LoreDataInvalidError(LoreStoreError):
    """Stored rows do not form valid domain objects."""


class LoreStore(ABC):
    @abstractmethod
    async def replace(self, entries: Iterable[LoreEntry]) -> LoreLoadSummary:
        """Replace the whole corpus atomically and return its new version."""


class LoreIndex(ABC):
    @abstractmethod
    async def search(
        self,
        terms: Sequence[str],
        top_k: int,
        params: Bm25Params,
    ) -> tuple[LoreHit, ...]:
        """Return the highest-scoring chunks for already analyzed terms."""

    @abstractmethod
    async def version(self) -> int:
        """Return the current corpus version."""


class LoreDocumentSource(ABC):
    @abstractmethod
    async def documents(self) -> tuple[LoreDocument, ...]:
        """Return every stored document, ordered by id."""

    @abstractmethod
    async def version(self) -> int:
        """Return the current corpus version."""
