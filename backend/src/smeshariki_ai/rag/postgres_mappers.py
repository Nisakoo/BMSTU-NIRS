"""Mapping of each knowledge aggregate to its ``rag_*`` rows and back.

A mapper owns everything the PostgreSQL store needs to know about one
aggregate: its root table, its child tables with the grouping key used when
reading, and both directions of the mapping. Child tables are listed in
insertion order; they are deleted in reverse order.
"""

from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from typing import Any, NamedTuple

from sqlalchemy import Table

from smeshariki_ai.rag import tables
from smeshariki_ai.rag.models import (
    Artifact,
    Character,
    Continuity,
    EntityType,
    Episode,
    Location,
    Work,
    normalize_name,
)

Row = dict[str, Any]
# Child rows grouped by the key of their table: the owner id, or a tuple of it
# and a position for rows nested one level deeper.
Grouped = dict[Any, list[Row]]


class Child(NamedTuple):
    table: Table
    key: tuple[str, ...]

    @property
    def owner(self) -> str:
        return self.key[0]


class AggregateMapper(ABC):
    root: Table
    children: tuple[Child, ...] = ()

    @abstractmethod
    def to_rows(self, entity: Any) -> tuple[Row, dict[Table, list[Row]]]:
        """The root row and the child rows of each child table."""

    @abstractmethod
    def from_rows(self, root: Row, children: Mapping[Table, Grouped]) -> Any:
        """Rebuild the aggregate; raises ``ValidationError`` on invalid rows."""


def _names(owner: str, entity: Character | Location | Artifact) -> list[Row]:
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


def _sources(entity: Any) -> list[Row]:
    return [
        source.model_dump(mode="json", exclude_none=True) for source in entity.sources
    ]


class _ContinuityMapper(AggregateMapper):
    root = tables.continuities

    def to_rows(self, entity: Continuity) -> tuple[Row, dict[Table, list[Row]]]:
        return {"id": entity.id, "name": entity.name}, {}

    def from_rows(self, root: Row, children: Mapping[Table, Grouped]) -> Continuity:
        return Continuity(id=root["id"], name=root["name"])


class _WorkMapper(AggregateMapper):
    root = tables.works

    def to_rows(self, entity: Work) -> tuple[Row, dict[Table, list[Row]]]:
        return {
            "id": entity.id,
            "title": entity.title,
            "kind": entity.kind.value,
            "continuity_id": entity.continuity,
        }, {}

    def from_rows(self, root: Row, children: Mapping[Table, Grouped]) -> Work:
        return Work.model_validate(
            {
                "id": root["id"],
                "title": root["title"],
                "kind": root["kind"],
                "continuity": root["continuity_id"],
            }
        )


class _CharacterMapper(AggregateMapper):
    root = tables.characters
    children = (
        Child(tables.character_names, ("character_id",)),
        Child(tables.character_versions, ("character_id",)),
        Child(
            tables.character_version_continuities, ("character_id", "version_position")
        ),
        Child(tables.relationships, ("character_id",)),
        Child(
            tables.relationship_continuities,
            ("character_id", "relationship_position"),
        ),
    )

    def to_rows(self, entity: Character) -> tuple[Row, dict[Table, list[Row]]]:
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
        root = {"id": entity.id, "species": entity.species, "sources": _sources(entity)}
        return root, {
            tables.character_names: _names(owner, entity),
            tables.character_versions: versions,
            tables.character_version_continuities: version_continuities,
            tables.relationships: relationships,
            tables.relationship_continuities: relationship_continuities,
        }

    def from_rows(self, root: Row, children: Mapping[Table, Grouped]) -> Character:
        names = children[tables.character_names][root["id"]]
        version_continuities = children[tables.character_version_continuities]
        relationship_continuities = children[tables.relationship_continuities]
        versions = [
            {
                "continuities": [
                    r["continuity_id"]
                    for r in version_continuities[(root["id"], row["position"])]
                ],
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
            for row in children[tables.character_versions][root["id"]]
        ]
        relationships = [
            {
                "to": row["to_character_id"],
                "type": row["type"],
                "continuities": [
                    r["continuity_id"]
                    for r in relationship_continuities[(root["id"], row["position"])]
                ],
                "description": row["description"],
                "sources": row["sources"],
            }
            for row in children[tables.relationships][root["id"]]
        ]
        return Character.model_validate(
            {
                "id": root["id"],
                "name": names[0]["value"] if names else None,
                "aliases": [r["value"] for r in names[1:]],
                "species": root["species"],
                "versions": versions,
                "relationships": relationships,
                "sources": root["sources"],
            }
        )


class _PlaceMapper(AggregateMapper):
    """Locations and artifacts share one shape: names, continuities, members."""

    def __init__(
        self,
        model: type[Location] | type[Artifact],
        root: Table,
        owner: str,
        names: Table,
        continuities: Table,
        members: tuple[Table, str],
        fields: tuple[str, ...],
    ) -> None:
        self.model = model
        self.root = root
        self.owner = owner
        self.names = names
        self.continuities = continuities
        self.members_table, self.members_field = members
        self.fields = fields
        self.children = tuple(
            Child(table, (owner,))
            for table in (names, continuities, self.members_table)
        )

    def to_rows(
        self, entity: Location | Artifact
    ) -> tuple[Row, dict[Table, list[Row]]]:
        root: Row = {"id": entity.id, "sources": _sources(entity)}
        for field in self.fields:
            value = getattr(entity, field)
            root[field] = list(value) if isinstance(value, tuple) else value
        return root, {
            self.names: _names(self.owner, entity),
            self.continuities: _members(
                self.owner, entity.id, "continuity_id", entity.continuities
            ),
            self.members_table: _members(
                self.owner,
                entity.id,
                "character_id",
                getattr(entity, self.members_field),
            ),
        }

    def from_rows(
        self, root: Row, children: Mapping[Table, Grouped]
    ) -> Location | Artifact:
        names = children[self.names][root["id"]]
        return self.model.model_validate(
            {
                "id": root["id"],
                "name": names[0]["value"] if names else None,
                "aliases": [r["value"] for r in names[1:]],
                **{field: root[field] for field in self.fields},
                "continuities": [
                    r["continuity_id"] for r in children[self.continuities][root["id"]]
                ],
                self.members_field: [
                    r["character_id"] for r in children[self.members_table][root["id"]]
                ],
                "sources": root["sources"],
            }
        )


class _EpisodeMapper(AggregateMapper):
    root = tables.episodes
    children = (
        Child(tables.episode_characters, ("episode_id",)),
        Child(tables.episode_locations, ("episode_id",)),
        Child(tables.episode_artifacts, ("episode_id",)),
        Child(tables.episode_interactions, ("episode_id",)),
    )

    def to_rows(self, entity: Episode) -> tuple[Row, dict[Table, list[Row]]]:
        owner = "episode_id"
        return {
            "id": entity.id,
            "work_id": entity.work,
            "season": entity.season,
            "number": entity.number,
            "title": entity.title,
            "normalized_title": normalize_name(entity.title),
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

    def from_rows(self, root: Row, children: Mapping[Table, Grouped]) -> Episode:
        def ids(table: Table, column: str) -> list[str]:
            return [row[column] for row in children[table][root["id"]]]

        return Episode.model_validate(
            {
                "id": root["id"],
                "work": root["work_id"],
                "season": root["season"],
                "number": root["number"],
                "title": root["title"],
                "characters": ids(tables.episode_characters, "character_id"),
                "locations": ids(tables.episode_locations, "location_id"),
                "artifacts": ids(tables.episode_artifacts, "artifact_id"),
                "interactions": [
                    {
                        "from": row["from_character_id"],
                        "to": row["to_character_id"],
                        "type": row["type"],
                        "description": row["description"],
                        "sources": row["sources"],
                    }
                    for row in children[tables.episode_interactions][root["id"]]
                ],
            }
        )


# Ordered so that the roots an aggregate references are inserted before it.
MAPPERS: dict[EntityType, AggregateMapper] = {
    EntityType.CONTINUITY: _ContinuityMapper(),
    EntityType.WORK: _WorkMapper(),
    EntityType.CHARACTER: _CharacterMapper(),
    EntityType.LOCATION: _PlaceMapper(
        Location,
        tables.locations,
        "location_id",
        tables.location_names,
        tables.location_continuities,
        (tables.location_residents, "residents"),
        ("description",),
    ),
    EntityType.ARTIFACT: _PlaceMapper(
        Artifact,
        tables.artifacts,
        "artifact_id",
        tables.artifact_names,
        tables.artifact_continuities,
        (tables.artifact_creators, "creators"),
        ("artifact_type", "description", "capabilities", "limitations"),
    ),
    EntityType.EPISODE: _EpisodeMapper(),
}
