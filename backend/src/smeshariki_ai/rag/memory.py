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
    Episode,
    KnowledgeEntity,
    KnowledgeSet,
    Work,
    entity_ref,
    normalize_name,
    references_of,
)
from smeshariki_ai.rag.ports import (
    EntityChange,
    FoundKnowledge,
    KnowledgeReader,
    KnowledgeStore,
    KnowledgeTransaction,
    LoadRecord,
    LoadSummary,
    Revision,
)

_LOOKED_UP = (
    EntityType.CHARACTER,
    EntityType.LOCATION,
    EntityType.ARTIFACT,
    EntityType.EPISODE,
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


def _keys(entity: KnowledgeEntity) -> set[str]:
    if isinstance(entity, Episode):
        return {entity.id, normalize_name(entity.title)}
    return {entity.id, *(normalize_name(n) for n in (entity.name, *entity.aliases))}


def _name(entity: KnowledgeEntity) -> str:
    return entity.title if isinstance(entity, Work | Episode) else entity.name


class InMemoryKnowledgeStore(KnowledgeStore, KnowledgeReader):
    def __init__(self) -> None:
        self._state = _State()
        self._lock = asyncio.Lock()

    async def find(self, key: str) -> FoundKnowledge:
        # A committed transaction replaces the state whole, so this is a snapshot.
        entities = self._state.entities
        grouped: dict[EntityType, list[KnowledgeEntity]] = {
            kind: [] for kind in _LOOKED_UP
        }
        for ref in sorted(entities, key=lambda item: item.id):
            if ref.type in grouped and key in _keys(entities[ref]):
                grouped[ref.type].append(entities[ref])
        found = KnowledgeSet(
            **{ENTITY_FIELDS[kind]: tuple(items) for kind, items in grouped.items()}
        )
        works = sorted(references_of(found).get(EntityType.WORK, ()))
        found = found.model_copy(
            update={
                "works": tuple(
                    entities[EntityRef(type=EntityType.WORK, id=work_id)]
                    for work_id in works
                )
            }
        )
        names = {
            kind: {
                entity_id: _name(entities[ref])
                for entity_id in ids
                if (ref := EntityRef(type=kind, id=entity_id)) in entities
            }
            for kind, ids in references_of(found).items()
        }
        return FoundKnowledge(entities=found, names=names)

    async def has_knowledge(self) -> bool:
        return any(r.summary is not None for r in self._state.loads.values())

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
