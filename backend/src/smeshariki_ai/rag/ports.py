"""Outbound ports of the knowledge store.

A load runs as one transaction: read every entity, then record the load, save
the changed aggregates with their revisions and complete the load. Concurrent
transactions are serialized, so a load always sees the state it writes on.

Lookups read through a separate port: they never wait for a load and see
either the state before it or after it.
"""

from abc import ABC, abstractmethod
from collections.abc import Sequence
from contextlib import AbstractAsyncContextManager
from datetime import datetime
from typing import Any, Literal

from pydantic import Field

from smeshariki_ai.rag.models import (
    EntityRef,
    EntityType,
    KnowledgeEntity,
    KnowledgeModel,
    KnowledgeSet,
)

ChangeOperation = Literal["create", "update"]


class KnowledgeStoreError(Exception):
    """Base error of the knowledge store."""


class KnowledgeStoreUnavailableError(KnowledgeStoreError):
    """The knowledge database cannot serve the request."""


class KnowledgeSchemaNotReadyError(KnowledgeStoreError):
    """The tables of structured knowledge do not exist: migrations are missing."""


class KnowledgeDataInvalidError(KnowledgeStoreError):
    """Stored rows do not form valid domain entities."""


class EntityChange(KnowledgeModel):
    operation: ChangeOperation
    entity: KnowledgeEntity


class ChangeCounts(KnowledgeModel):
    added: int = Field(default=0, ge=0)
    updated: int = Field(default=0, ge=0)
    unchanged: int = Field(default=0, ge=0)


class LoadSummary(KnowledgeModel):
    finished_at: datetime
    duration_ms: int = Field(ge=0)
    entity_count: int = Field(ge=0)
    # Counts of each entity type, keyed by the ``KnowledgeSet`` field.
    counts: dict[str, ChangeCounts]


class LoadRecord(KnowledgeModel):
    id: int
    started_at: datetime
    summary: LoadSummary | None


class Revision(KnowledgeModel):
    revision: int = Field(ge=1)
    operation: Literal["create", "update", "delete"]
    load_id: int
    # Version of the entity format the payload is written in.
    format_version: int = Field(ge=1)
    payload: dict[str, Any]


class KnowledgeTransaction(ABC):
    @abstractmethod
    async def read_all(self) -> KnowledgeSet:
        """Every stored entity, ordered by ``id`` within each type."""

    @abstractmethod
    async def start_load(self, started_at: datetime) -> int:
        """Record a load and return its id."""

    @abstractmethod
    async def save(self, load_id: int, changes: Sequence[EntityChange]) -> None:
        """Replace each changed aggregate and append its revision."""

    @abstractmethod
    async def finish_load(self, load_id: int, summary: LoadSummary) -> None:
        """Complete the load recorded by ``start_load``."""

    @abstractmethod
    async def read_load(self, load_id: int) -> LoadRecord | None:
        """The load with this id, if it is stored."""

    @abstractmethod
    async def read_revisions(self, ref: EntityRef) -> tuple[Revision, ...]:
        """Revisions of one entity, oldest first."""


class KnowledgeStore(ABC):
    @abstractmethod
    def transaction(self) -> AbstractAsyncContextManager[KnowledgeTransaction]:
        """Open a serialized transaction; an exception inside rolls it back."""


class FoundKnowledge(KnowledgeModel):
    """Entities matching a lookup key and the names of what they reference."""

    # Only characters, locations, artifacts and episodes are looked up.
    entities: KnowledgeSet = KnowledgeSet()
    # Name or title of each referenced continuity, work, character, location
    # and artifact, keyed by its type and id.
    names: dict[EntityType, dict[str, str]] = {}


class KnowledgeReader(ABC):
    @abstractmethod
    async def find(self, key: str) -> FoundKnowledge:
        """Entities whose normalized name, alias, title or id equals ``key``."""

    @abstractmethod
    async def has_knowledge(self) -> bool:
        """Whether at least one load has completed."""
