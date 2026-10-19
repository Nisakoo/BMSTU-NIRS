"""In-memory knowledge store for tests; it keeps state only in the process."""

import asyncio
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from datetime import datetime

from smeshariki_ai.rag.models import (
    ENTITY_FIELDS,
    KNOWLEDGE_FORMAT_VERSION,
    EntityRef,
    EntityType,
    KnowledgeEntity,
    KnowledgeSet,
    entity_ref,
)
from smeshariki_ai.rag.ports import (
    EntityChange,
    KnowledgeStore,
    KnowledgeTransaction,
    LoadRecord,
    LoadSummary,
    Revision,
)


class _State:
    def __init__(self) -> None:
        self.entities: dict[EntityRef, KnowledgeEntity] = {}
        self.revisions: dict[EntityRef, list[Revision]] = {}
        self.loads: dict[int, LoadRecord] = {}

    def copy(self) -> "_State":
        # Models are immutable, so copying the containers isolates a transaction.
        state = _State()
        state.entities = dict(self.entities)
        state.revisions = {ref: list(items) for ref, items in self.revisions.items()}
        state.loads = dict(self.loads)
        return state


class InMemoryKnowledgeStore(KnowledgeStore):
    def __init__(self) -> None:
        self._state = _State()
        self._lock = asyncio.Lock()

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[KnowledgeTransaction]:
        async with self._lock:
            working = self._state.copy()
            yield _InMemoryTransaction(working)
            self._state = working


class _InMemoryTransaction(KnowledgeTransaction):
    def __init__(self, state: _State) -> None:
        self._state = state

    async def read_all(self) -> KnowledgeSet:
        grouped: dict[EntityType, list[KnowledgeEntity]] = {
            kind: [] for kind in EntityType
        }
        for ref in sorted(self._state.entities, key=lambda item: item.id):
            grouped[ref.type].append(self._state.entities[ref])
        return KnowledgeSet(
            **{ENTITY_FIELDS[kind]: tuple(items) for kind, items in grouped.items()}
        )

    async def start_load(self, started_at: datetime) -> int:
        load_id = max(self._state.loads, default=0) + 1
        self._state.loads[load_id] = LoadRecord(
            id=load_id, started_at=started_at, summary=None
        )
        return load_id

    async def save(self, load_id: int, changes: Sequence[EntityChange]) -> None:
        for change in changes:
            ref = entity_ref(change.entity)
            self._state.entities[ref] = change.entity
            history = self._state.revisions.setdefault(ref, [])
            history.append(
                Revision(
                    revision=len(history) + 1,
                    operation=change.operation,
                    load_id=load_id,
                    format_version=KNOWLEDGE_FORMAT_VERSION,
                    payload=change.entity.model_dump(mode="json", by_alias=True),
                )
            )

    async def finish_load(self, load_id: int, summary: LoadSummary) -> None:
        record = self._state.loads[load_id]
        self._state.loads[load_id] = record.model_copy(update={"summary": summary})

    async def read_load(self, load_id: int) -> LoadRecord | None:
        return self._state.loads.get(load_id)

    async def read_revisions(self, ref: EntityRef) -> tuple[Revision, ...]:
        return tuple(self._state.revisions.get(ref, ()))
