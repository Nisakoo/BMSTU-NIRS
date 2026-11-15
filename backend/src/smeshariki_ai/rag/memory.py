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
    SUGGESTION_LIMIT,
    SUGGESTION_THRESHOLD,
    EntityChange,
    FoundKnowledge,
    JournalOperation,
    KnowledgeReader,
    KnowledgeSnapshot,
    KnowledgeStore,
    KnowledgeTransaction,
    LoadRecord,
    LoadSummary,
    LookupSuggestion,
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


def _knowledge(state: _State) -> KnowledgeSet:
    grouped: dict[EntityType, list[KnowledgeEntity]] = {kind: [] for kind in EntityType}
    for ref in sorted(state.entities, key=lambda item: item.id):
        grouped[ref.type].append(state.entities[ref])
    return KnowledgeSet(
        **{ENTITY_FIELDS[kind]: tuple(items) for kind, items in grouped.items()}
    )


def _revision_index(state: _State) -> dict[EntityRef, int]:
    return {
        ref: max(revision.revision for revision in history)
        for ref, history in state.revisions.items()
        if history
    }


def _trigrams(value: str) -> set[str]:
    padded = f"  {value} "
    return {padded[index : index + 3] for index in range(len(padded) - 2)}


def _similarity(left: str, right: str) -> float:
    first, second = _trigrams(left), _trigrams(right)
    if not first or not second:
        return 0.0
    common = len(first & second)
    return common / (len(first) + len(second) - common)


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

    async def suggest(
        self, key: str, limit: int = SUGGESTION_LIMIT
    ) -> tuple[LookupSuggestion, ...]:
        if limit <= 0:
            return ()
        order = {kind: index for index, kind in enumerate(EntityType)}
        candidates: list[tuple[float, int, EntityType, str, str]] = []
        entities = self._state.entities
        for ref in sorted(entities, key=lambda item: item.id):
            if ref.type not in _LOOKED_UP:
                continue
            entity = entities[ref]
            score = max(_similarity(key, value) for value in _keys(entity))
            if score >= SUGGESTION_THRESHOLD:
                candidates.append(
                    (score, order[ref.type], ref.type, ref.id, _name(entity))
                )
        candidates.sort(key=lambda item: (-item[0], item[1], item[3]))
        return tuple(
            LookupSuggestion(type=kind, id=entity_id, name=name)
            for _, _, kind, entity_id, name in candidates[:limit]
        )

    async def has_knowledge(self) -> bool:
        return any(r.summary is not None for r in self._state.loads.values())

    async def snapshot(self) -> KnowledgeSnapshot:
        state = self._state
        return KnowledgeSnapshot(
            knowledge=_knowledge(state), revisions=_revision_index(state)
        )

    async def revision_history(self, ref: EntityRef) -> tuple[Revision, ...]:
        return tuple(self._state.revisions.get(ref, ()))

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
        return _knowledge(self._state)

    async def revision_index(self) -> dict[EntityRef, int]:
        return _revision_index(self._state)

    async def start_load(
        self, started_at: datetime, operation: JournalOperation = "load"
    ) -> int:
        load_id = max(self._state.loads, default=0) + 1
        self._state.loads[load_id] = LoadRecord(
            id=load_id, started_at=started_at, operation=operation, summary=None
        )
        return load_id

    async def save(self, load_id: int, changes: Sequence[EntityChange]) -> None:
        for change in changes:
            ref = entity_ref(change.entity)
            if change.operation == "delete":
                self._state.entities.pop(ref, None)
            else:
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
