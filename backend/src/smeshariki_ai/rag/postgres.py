"""PostgreSQL implementation of the knowledge store over the ``rag_*`` tables.

Reading issues one query per table and saving one statement per table, so the
number of queries does not grow with the number of entities. Saving replaces
the child rows of each changed aggregate and updates its root row in place:
other aggregates reference only root rows, so they are never touched.
"""

from collections import defaultdict
from collections.abc import AsyncIterator, Callable, Iterator, Sequence
from contextlib import asynccontextmanager, contextmanager
from datetime import datetime
from typing import Any

from asyncpg import PostgresError
from sqlalchemy import Table, delete, func, insert, select, update
from sqlalchemy.dialects.postgresql import insert as upsert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from smeshariki_ai.rag import tables
from smeshariki_ai.rag.models import (
    ENTITY_TYPES,
    Artifact,
    Character,
    Continuity,
    EntityRef,
    EntityType,
    Episode,
    KnowledgeEntity,
    KnowledgeSet,
    Location,
    Work,
    entity_ref,
    normalize_name,
)
from smeshariki_ai.rag.ports import (
    EntityChange,
    KnowledgeSchemaNotReadyError,
    KnowledgeStore,
    KnowledgeStoreUnavailableError,
    KnowledgeTransaction,
    LoadRecord,
    LoadSummary,
    Revision,
)

# Serializes loads across connections: b"rag_load" as a 64-bit integer.
_LOAD_LOCK_KEY = int.from_bytes(b"rag_load", "big")
_UNDEFINED_TABLE = "42P01"

Rows = dict[Table, list[dict[str, Any]]]

# Root tables in the order their rows may be inserted.
_ROOTS: dict[EntityType, Table] = {
    EntityType.CONTINUITY: tables.continuities,
    EntityType.WORK: tables.works,
    EntityType.CHARACTER: tables.characters,
    EntityType.LOCATION: tables.locations,
    EntityType.ARTIFACT: tables.artifacts,
    EntityType.EPISODE: tables.episodes,
}
# Child tables of each aggregate in insertion order, with their owner column.
_CHILDREN: dict[EntityType, tuple[tuple[Table, str], ...]] = {
    EntityType.CONTINUITY: (),
    EntityType.WORK: (),
    EntityType.CHARACTER: (
        (tables.character_names, "character_id"),
        (tables.character_versions, "character_id"),
        (tables.character_version_continuities, "character_id"),
        (tables.relationships, "character_id"),
        (tables.relationship_continuities, "character_id"),
    ),
    EntityType.LOCATION: (
        (tables.location_names, "location_id"),
        (tables.location_continuities, "location_id"),
        (tables.location_residents, "location_id"),
    ),
    EntityType.ARTIFACT: (
        (tables.artifact_names, "artifact_id"),
        (tables.artifact_continuities, "artifact_id"),
        (tables.artifact_creators, "artifact_id"),
    ),
    EntityType.EPISODE: (
        (tables.episode_characters, "episode_id"),
        (tables.episode_locations, "episode_id"),
        (tables.episode_artifacts, "episode_id"),
        (tables.episode_interactions, "episode_id"),
    ),
}


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

    async def _rows(self, table: Table, *order: str) -> list[dict[str, Any]]:
        statement = select(table).order_by(*(table.c[name] for name in order))
        result = await self._connection.execute(statement)
        return [dict(row) for row in result.mappings()]

    async def _grouped(
        self, table: Table, *key: str
    ) -> dict[Any, list[dict[str, Any]]]:
        """Rows grouped by ``key`` (one column or a tuple), in ``position`` order."""

        groups: dict[Any, list[dict[str, Any]]] = defaultdict(list)
        for row in await self._rows(table, *key, "position"):
            values = tuple(row[name] for name in key)
            groups[values[0] if len(values) == 1 else values].append(row)
        return groups

    async def read_all(self) -> KnowledgeSet:
        return KnowledgeSet(
            continuities=await self._read_continuities(),
            works=await self._read_works(),
            episodes=await self._read_episodes(),
            characters=await self._read_characters(),
            locations=await self._read_places(
                Location,
                tables.locations,
                "location_id",
                (tables.location_names, tables.location_continuities),
                (tables.location_residents, "residents"),
                ("description",),
            ),
            artifacts=await self._read_places(
                Artifact,
                tables.artifacts,
                "artifact_id",
                (tables.artifact_names, tables.artifact_continuities),
                (tables.artifact_creators, "creators"),
                ("artifact_type", "description", "capabilities", "limitations"),
            ),
        )

    async def _read_continuities(self) -> tuple[Continuity, ...]:
        return tuple(
            Continuity(id=row["id"], name=row["name"])
            for row in await self._rows(tables.continuities, "id")
        )

    async def _read_works(self) -> tuple[Work, ...]:
        return tuple(
            Work.model_validate(
                {
                    "id": row["id"],
                    "title": row["title"],
                    "kind": row["kind"],
                    "continuity": row["continuity_id"],
                }
            )
            for row in await self._rows(tables.works, "id")
        )

    async def _read_episodes(self) -> tuple[Episode, ...]:
        characters = await self._grouped(tables.episode_characters, "episode_id")
        locations = await self._grouped(tables.episode_locations, "episode_id")
        artifacts = await self._grouped(tables.episode_artifacts, "episode_id")
        interactions = await self._grouped(tables.episode_interactions, "episode_id")
        return tuple(
            Episode.model_validate(
                {
                    "id": row["id"],
                    "work": row["work_id"],
                    "season": row["season"],
                    "number": row["number"],
                    "title": row["title"],
                    "characters": [r["character_id"] for r in characters[row["id"]]],
                    "locations": [r["location_id"] for r in locations[row["id"]]],
                    "artifacts": [r["artifact_id"] for r in artifacts[row["id"]]],
                    "interactions": [
                        {
                            "from": r["from_character_id"],
                            "to": r["to_character_id"],
                            "type": r["type"],
                            "description": r["description"],
                            "sources": r["sources"],
                        }
                        for r in interactions[row["id"]]
                    ],
                }
            )
            for row in await self._rows(tables.episodes, "id")
        )

    async def _read_characters(self) -> tuple[Character, ...]:
        names = await self._grouped(tables.character_names, "character_id")
        versions = await self._grouped(tables.character_versions, "character_id")
        version_continuities = await self._grouped(
            tables.character_version_continuities, "character_id", "version_position"
        )
        relationships = await self._grouped(tables.relationships, "character_id")
        relationship_continuities = await self._grouped(
            tables.relationship_continuities, "character_id", "relationship_position"
        )

        def version(row: dict[str, Any]) -> dict[str, Any]:
            key = (row["character_id"], row["position"])
            return {
                "continuities": [r["continuity_id"] for r in version_continuities[key]],
                "age_group": row["age_group"],
                "traits": row["traits"],
                "speech_style": {
                    "register": row["speech_register"],
                    "markers": row["speech_markers"],
                    "constraints": row["speech_constraints"],
                },
                "catchphrases": row["catchphrases"],
                "sources": row["sources"],
            }

        def relationship(row: dict[str, Any]) -> dict[str, Any]:
            key = (row["character_id"], row["position"])
            return {
                "to": row["to_character_id"],
                "type": row["type"],
                "continuities": [
                    r["continuity_id"] for r in relationship_continuities[key]
                ],
                "description": row["description"],
                "sources": row["sources"],
            }

        return tuple(
            Character.model_validate(
                {
                    "id": row["id"],
                    "name": names[row["id"]][0]["value"],
                    "aliases": [r["value"] for r in names[row["id"]][1:]],
                    "species": row["species"],
                    "versions": [version(r) for r in versions[row["id"]]],
                    "relationships": [
                        relationship(r) for r in relationships[row["id"]]
                    ],
                    "sources": row["sources"],
                }
            )
            for row in await self._rows(tables.characters, "id")
        )

    async def _read_places(
        self,
        model: type[Location] | type[Artifact],
        root: Table,
        owner: str,
        names_and_continuities: tuple[Table, Table],
        members: tuple[Table, str],
        fields: tuple[str, ...],
    ) -> tuple[Any, ...]:
        """Locations and artifacts share one shape: names, continuities, members."""

        names_table, continuities_table = names_and_continuities
        members_table, members_field = members
        names = await self._grouped(names_table, owner)
        continuities = await self._grouped(continuities_table, owner)
        member_rows = await self._grouped(members_table, owner)
        return tuple(
            model.model_validate(
                {
                    "id": row["id"],
                    "name": names[row["id"]][0]["value"],
                    "aliases": [r["value"] for r in names[row["id"]][1:]],
                    **{field: row[field] for field in fields},
                    "continuities": [
                        r["continuity_id"] for r in continuities[row["id"]]
                    ],
                    members_field: [r["character_id"] for r in member_rows[row["id"]]],
                    "sources": row["sources"],
                }
            )
            for row in await self._rows(root, "id")
        )

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
            for table, owner in reversed(_CHILDREN[kind]):
                await self._connection.execute(
                    delete(table).where(table.c[owner].in_(ids))
                )

        children: Rows = defaultdict(list)
        for kind, root in _ROOTS.items():
            if kind not in by_type:
                continue
            roots = []
            for entity in by_type[kind]:
                row, child_rows = _ROW_BUILDERS[kind](entity)
                roots.append(row)
                for table, items in child_rows.items():
                    children[table].extend(items)
            await self._upsert(root, roots)

        for kind in _ROOTS:
            for table, _ in _CHILDREN[kind]:
                if children[table]:
                    await self._connection.execute(insert(table), children[table])

        await self._append_revisions(load_id, changes)

    async def _upsert(self, table: Table, rows: list[dict[str, Any]]) -> None:
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
                report=row["report"],
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
                payload=row["payload"],
            )
            for row in rows
        )


def _names(owner: str, entity: Any) -> list[dict[str, Any]]:
    return [
        {
            owner: entity.id,
            "position": position,
            "value": value,
            "normalized": normalize_name(value),
        }
        for position, value in enumerate((entity.name, *entity.aliases))
    ]


def _members(owner: str, owner_id: str, column: str, values: Sequence[str]) -> list:
    return [
        {owner: owner_id, "position": position, column: value}
        for position, value in enumerate(values)
    ]


def _sources(entity: Any) -> list[dict[str, Any]]:
    return [
        source.model_dump(mode="json", exclude_none=True) for source in entity.sources
    ]


def _continuity_rows(entity: Continuity) -> tuple[dict[str, Any], Rows]:
    return {"id": entity.id, "name": entity.name}, {}


def _work_rows(entity: Work) -> tuple[dict[str, Any], Rows]:
    return {
        "id": entity.id,
        "title": entity.title,
        "kind": entity.kind.value,
        "continuity_id": entity.continuity,
    }, {}


def _episode_rows(entity: Episode) -> tuple[dict[str, Any], Rows]:
    owner = "episode_id"
    return {
        "id": entity.id,
        "work_id": entity.work,
        "season": entity.season,
        "number": entity.number,
        "title": entity.title,
    }, {
        tables.episode_characters: _members(
            owner, entity.id, "character_id", entity.characters
        ),
        tables.episode_locations: _members(
            owner, entity.id, "location_id", entity.locations
        ),
        tables.episode_artifacts: _members(
            owner, entity.id, "artifact_id", entity.artifacts
        ),
        tables.episode_interactions: [
            {
                owner: entity.id,
                "position": position,
                "from_character_id": item.from_,
                "to_character_id": item.to,
                "type": item.type.value,
                "description": item.description,
                "sources": _sources(item),
            }
            for position, item in enumerate(entity.interactions)
        ],
    }


def _character_rows(entity: Character) -> tuple[dict[str, Any], Rows]:
    owner = "character_id"
    versions, version_continuities = [], []
    for position, version in enumerate(entity.versions):
        versions.append(
            {
                owner: entity.id,
                "position": position,
                "age_group": version.age_group.value,
                "traits": list(version.traits),
                "speech_register": version.speech_style.register_,
                "speech_markers": list(version.speech_style.markers),
                "speech_constraints": list(version.speech_style.constraints),
                "catchphrases": list(version.catchphrases),
                "sources": _sources(version),
            }
        )
        version_continuities.extend(
            {
                owner: entity.id,
                "version_position": position,
                "position": index,
                "continuity_id": continuity,
            }
            for index, continuity in enumerate(version.continuities)
        )
    relationships, relationship_continuities = [], []
    for position, relationship in enumerate(entity.relationships):
        relationships.append(
            {
                owner: entity.id,
                "position": position,
                "to_character_id": relationship.to,
                "type": relationship.type.value,
                "description": relationship.description,
                "sources": _sources(relationship),
            }
        )
        relationship_continuities.extend(
            {
                owner: entity.id,
                "relationship_position": position,
                "position": index,
                "continuity_id": continuity,
            }
            for index, continuity in enumerate(relationship.continuities)
        )
    return {"id": entity.id, "species": entity.species, "sources": _sources(entity)}, {
        tables.character_names: _names(owner, entity),
        tables.character_versions: versions,
        tables.character_version_continuities: version_continuities,
        tables.relationships: relationships,
        tables.relationship_continuities: relationship_continuities,
    }


def _location_rows(entity: Location) -> tuple[dict[str, Any], Rows]:
    owner = "location_id"
    return {
        "id": entity.id,
        "description": entity.description,
        "sources": _sources(entity),
    }, {
        tables.location_names: _names(owner, entity),
        tables.location_continuities: _members(
            owner, entity.id, "continuity_id", entity.continuities
        ),
        tables.location_residents: _members(
            owner, entity.id, "character_id", entity.residents
        ),
    }


def _artifact_rows(entity: Artifact) -> tuple[dict[str, Any], Rows]:
    owner = "artifact_id"
    return {
        "id": entity.id,
        "artifact_type": entity.artifact_type,
        "description": entity.description,
        "capabilities": list(entity.capabilities),
        "limitations": list(entity.limitations),
        "sources": _sources(entity),
    }, {
        tables.artifact_names: _names(owner, entity),
        tables.artifact_continuities: _members(
            owner, entity.id, "continuity_id", entity.continuities
        ),
        tables.artifact_creators: _members(
            owner, entity.id, "character_id", entity.creators
        ),
    }


_ROW_BUILDERS: dict[EntityType, Callable[[Any], tuple[dict[str, Any], Rows]]] = {
    EntityType.CONTINUITY: _continuity_rows,
    EntityType.WORK: _work_rows,
    EntityType.EPISODE: _episode_rows,
    EntityType.CHARACTER: _character_rows,
    EntityType.LOCATION: _location_rows,
    EntityType.ARTIFACT: _artifact_rows,
}
