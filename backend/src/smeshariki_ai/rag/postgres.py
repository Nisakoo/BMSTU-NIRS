"""PostgreSQL implementation of the knowledge store over the ``rag_*`` tables.

Reading issues one query per table and saving one statement per table, so the
number of queries does not grow with the number of entities. Saving replaces
the child rows of each changed aggregate and updates its root row in place:
other aggregates reference only root rows, so they are never touched. How an
aggregate maps to rows is described in ``postgres_mappers``.
"""

from collections import defaultdict
from collections.abc import AsyncIterator, Iterator, Sequence
from contextlib import asynccontextmanager, contextmanager
from datetime import datetime
from typing import Any

from asyncpg import PostgresError
from pydantic import ValidationError
from sqlalchemy import Table, delete, func, insert, select, update
from sqlalchemy.dialects.postgresql import insert as upsert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from smeshariki_ai.rag import tables
from smeshariki_ai.rag.models import (
    ENTITY_FIELDS,
    ENTITY_TYPES,
    KNOWLEDGE_FORMAT_VERSION,
    EntityRef,
    EntityType,
    KnowledgeEntity,
    KnowledgeSet,
    entity_ref,
)
from smeshariki_ai.rag.ports import (
    EntityChange,
    KnowledgeDataInvalidError,
    KnowledgeSchemaNotReadyError,
    KnowledgeStore,
    KnowledgeStoreUnavailableError,
    KnowledgeTransaction,
    LoadRecord,
    LoadSummary,
    Revision,
)
from smeshariki_ai.rag.postgres_mappers import MAPPERS, Grouped, Row

# Serializes loads across connections: b"rag_load" as a 64-bit integer.
_LOAD_LOCK_KEY = int.from_bytes(b"rag_load", "big")
_UNDEFINED_TABLE = "42P01"


@contextmanager
def _translate_errors() -> Iterator[None]:
    try:
        yield
    except SQLAlchemyError as error:
        if getattr(getattr(error, "orig", None), "sqlstate", None) == _UNDEFINED_TABLE:
            raise KnowledgeSchemaNotReadyError from error
        # The cause is chained, but its text (SQL, parameters) is never shown.
        raise KnowledgeStoreUnavailableError from error
    except (PostgresError, OSError) as error:
        raise KnowledgeStoreUnavailableError from error


class PostgresKnowledgeStore(KnowledgeStore):
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[KnowledgeTransaction]:
        with _translate_errors():
            async with self._engine.begin() as connection:
                await connection.execute(
                    select(func.pg_advisory_xact_lock(_LOAD_LOCK_KEY))
                )
                yield _PostgresTransaction(connection)


class _PostgresTransaction(KnowledgeTransaction):
    def __init__(self, connection: AsyncConnection) -> None:
        self._connection = connection

    async def _rows(self, table: Table, *order: str) -> list[Row]:
        statement = select(table).order_by(*(table.c[name] for name in order))
        result = await self._connection.execute(statement)
        return [dict(row) for row in result.mappings()]

    async def _grouped(self, table: Table, *key: str) -> Grouped:
        """Rows grouped by ``key`` (one column or a tuple), in ``position`` order."""

        groups: Grouped = defaultdict(list)
        for row in await self._rows(table, *key, "position"):
            values = tuple(row[name] for name in key)
            groups[values[0] if len(values) == 1 else values].append(row)
        return groups

    async def read_all(self) -> KnowledgeSet:
        entities: dict[str, tuple[Any, ...]] = {}
        for kind, mapper in MAPPERS.items():
            children = {
                child.table: await self._grouped(child.table, *child.key)
                for child in mapper.children
            }
            roots = await self._rows(mapper.root, "id")
            try:
                entities[ENTITY_FIELDS[kind]] = tuple(
                    mapper.from_rows(root, children) for root in roots
                )
            except ValidationError as error:
                # The rows are not shown: they may hold anything.
                raise KnowledgeDataInvalidError from error
        return KnowledgeSet(**entities)

    async def start_load(self, started_at: datetime) -> int:
        return await self._connection.scalar(
            insert(tables.loads)
            .values(started_at=started_at)
            .returning(tables.loads.c.id)
        )

    async def save(self, load_id: int, changes: Sequence[EntityChange]) -> None:
        if not changes:
            return
        by_type: dict[EntityType, list[KnowledgeEntity]] = defaultdict(list)
        for change in changes:
            by_type[ENTITY_TYPES[type(change.entity)]].append(change.entity)

        # Child rows go first, so a name may move between aggregates of one load.
        for kind, entities in by_type.items():
            ids = [entity.id for entity in entities]
            for child in reversed(MAPPERS[kind].children):
                await self._connection.execute(
                    delete(child.table).where(child.table.c[child.owner].in_(ids))
                )

        children: dict[Table, list[Row]] = defaultdict(list)
        for kind, mapper in MAPPERS.items():
            if kind not in by_type:
                continue
            roots = []
            for entity in by_type[kind]:
                root, child_rows = mapper.to_rows(entity)
                roots.append(root)
                for table, rows in child_rows.items():
                    children[table].extend(rows)
            await self._upsert(mapper.root, roots)

        for mapper in MAPPERS.values():
            for child in mapper.children:
                if children[child.table]:
                    await self._connection.execute(
                        insert(child.table), children[child.table]
                    )

        await self._append_revisions(load_id, changes)

    async def _upsert(self, table: Table, rows: list[Row]) -> None:
        statement = upsert(table)
        columns = [name for name in rows[0] if name != "id"]
        statement = statement.on_conflict_do_update(
            index_elements=[table.c.id],
            set_={
                **{name: statement.excluded[name] for name in columns},
                "updated_at": func.now(),
            },
        )
        await self._connection.execute(statement, rows)

    async def _append_revisions(
        self, load_id: int, changes: Sequence[EntityChange]
    ) -> None:
        refs = [entity_ref(change.entity) for change in changes]
        latest = select(
            tables.revisions.c.entity_type,
            tables.revisions.c.entity_id,
            func.max(tables.revisions.c.revision),
        ).where(tables.revisions.c.entity_id.in_({ref.id for ref in refs}))
        latest = latest.group_by(
            tables.revisions.c.entity_type, tables.revisions.c.entity_id
        )
        current = {
            (kind, entity_id): revision
            for kind, entity_id, revision in await self._connection.execute(latest)
        }
        await self._connection.execute(
            insert(tables.revisions),
            [
                {
                    "load_id": load_id,
                    "entity_type": ref.type.value,
                    "entity_id": ref.id,
                    "revision": current.get((ref.type.value, ref.id), 0) + 1,
                    "operation": change.operation,
                    "format_version": KNOWLEDGE_FORMAT_VERSION,
                    "payload": change.entity.model_dump(mode="json", by_alias=True),
                }
                for ref, change in zip(refs, changes, strict=True)
            ],
        )

    async def finish_load(self, load_id: int, summary: LoadSummary) -> None:
        await self._connection.execute(
            update(tables.loads)
            .where(tables.loads.c.id == load_id)
            .values(**summary.model_dump())
        )

    async def read_load(self, load_id: int) -> LoadRecord | None:
        row = (
            (
                await self._connection.execute(
                    select(tables.loads).where(tables.loads.c.id == load_id)
                )
            )
            .mappings()
            .first()
        )
        if row is None:
            return None
        summary = None
        if row["finished_at"] is not None:
            summary = LoadSummary(
                finished_at=row["finished_at"],
                duration_ms=row["duration_ms"],
                entity_count=row["entity_count"],
                counts=row["counts"],
            )
        return LoadRecord(id=row["id"], started_at=row["started_at"], summary=summary)

    async def read_revisions(self, ref: EntityRef) -> tuple[Revision, ...]:
        statement = (
            select(tables.revisions)
            .where(
                tables.revisions.c.entity_type == ref.type.value,
                tables.revisions.c.entity_id == ref.id,
            )
            .order_by(tables.revisions.c.revision)
        )
        rows = (await self._connection.execute(statement)).mappings()
        return tuple(
            Revision(
                revision=row["revision"],
                operation=row["operation"],
                load_id=row["load_id"],
                format_version=row["format_version"],
                payload=row["payload"],
            )
            for row in rows
        )
