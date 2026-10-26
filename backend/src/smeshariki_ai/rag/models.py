"""Domain model of structured knowledge about the Smeshariki universe.

Models are strict by default. Only tuples and enums accept the looser input
YAML produces (lists and plain strings), because YAML has neither type; their
items and values are still validated strictly.
"""

from __future__ import annotations

import unicodedata
from enum import StrEnum
from typing import Annotated, Any, NamedTuple

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)
from pydantic_core import PydanticCustomError

# Version of the entity format used by package files and revision snapshots.
KNOWLEDGE_FORMAT_VERSION = 1

SLUG_PATTERN = r"^[a-z0-9]+(_[a-z0-9]+)*$"
TIMECODE_PATTERN = r"^(?:\d{2}:)?[0-5]\d:[0-5]\d$"

Slug = Annotated[str, StringConstraints(pattern=SLUG_PATTERN)]
NonEmptyText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
Timecode = Annotated[str, StringConstraints(pattern=TIMECODE_PATTERN)]
PositiveInt = Annotated[int, Field(ge=1)]


def _unique(values: tuple[Any, ...]) -> tuple[Any, ...]:
    if len(set(values)) != len(values):
        raise PydanticCustomError("duplicate_value", "значения в списке повторяются")
    return values


_UNIQUE = (
    AfterValidator(_unique),
    Field(strict=False, json_schema_extra={"uniqueItems": True}),
)
SlugList = Annotated[tuple[Slug, ...], *_UNIQUE]
TextList = Annotated[tuple[NonEmptyText, ...], *_UNIQUE]
NonEmptySlugList = Annotated[tuple[Slug, ...], *_UNIQUE, Field(min_length=1)]
NonEmptyTextList = Annotated[tuple[NonEmptyText, ...], *_UNIQUE, Field(min_length=1)]


def normalize_name(value: str) -> str:
    """Comparison key of a name or alias: NFC, case-folded, single-spaced, ё → е.

    NFC first joins letters typed as a base and a combining mark, so "ё" made
    of "е" and a diaeresis gives the same key as the single character.
    """

    folded = unicodedata.normalize("NFC", value).casefold()
    return " ".join(folded.split()).replace("ё", "е")


class KnowledgeModel(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)


class AgeGroup(StrEnum):
    CHILD = "child"
    TEEN = "teen"
    ADULT = "adult"
    ELDERLY = "elderly"


class WorkKind(StrEnum):
    SERIES = "series"
    FILM = "film"


class RelationshipType(StrEnum):
    FRIENDSHIP = "friendship"
    NEIGHBORHOOD = "neighborhood"
    AFFECTION = "affection"
    MENTOR = "mentor"
    GUARDIAN = "guardian"

    @property
    def symmetric(self) -> bool:
        return self in _SYMMETRIC_RELATIONSHIPS


class InteractionType(StrEnum):
    CONFLICT = "conflict"
    SUPPORT = "support"
    EMPATHY = "empathy"

    @property
    def symmetric(self) -> bool:
        return self in _SYMMETRIC_INTERACTIONS


_SYMMETRIC_RELATIONSHIPS = frozenset(
    {RelationshipType.FRIENDSHIP, RelationshipType.NEIGHBORHOOD}
)
_SYMMETRIC_INTERACTIONS = frozenset({InteractionType.CONFLICT})


class SourceRef(KnowledgeModel):
    episode: Slug | None = None
    timecode: Timecode | None = None
    document: NonEmptyText | None = None
    locator: NonEmptyText | None = None
    note: NonEmptyText | None = None

    @model_validator(mode="after")
    def _one_kind(self) -> SourceRef:
        from_episode = self.episode is not None
        from_document = self.document is not None
        misplaced = (from_episode and self.locator is not None) or (
            from_document and self.timecode is not None
        )
        if from_episode == from_document or misplaced:
            raise PydanticCustomError(
                "invalid_source",
                "укажите либо episode (с необязательным timecode), "
                "либо document (с необязательным locator)",
            )
        return self


SourceList = Annotated[tuple[SourceRef, ...], *_UNIQUE]


class Continuity(KnowledgeModel):
    id: Slug
    name: NonEmptyText


class Work(KnowledgeModel):
    id: Slug
    title: NonEmptyText
    kind: WorkKind = Field(strict=False)
    continuity: Slug


class Interaction(KnowledgeModel):
    from_: Slug = Field(alias="from")
    to: Slug
    type: InteractionType = Field(strict=False)
    description: NonEmptyText
    sources: SourceList = ()


class Episode(KnowledgeModel):
    id: Slug
    work: Slug
    season: PositiveInt | None = None
    number: PositiveInt
    title: NonEmptyText
    characters: SlugList = ()
    locations: SlugList = ()
    artifacts: SlugList = ()
    interactions: Annotated[tuple[Interaction, ...], *_UNIQUE] = ()


class SpeechStyle(KnowledgeModel):
    # A field named ``register`` shadows a ``BaseModel`` attribute.
    register_: NonEmptyText = Field(alias="register")
    markers: TextList = ()
    constraints: TextList = ()


class CharacterVersion(KnowledgeModel):
    continuities: NonEmptySlugList
    age_group: AgeGroup = Field(strict=False)
    traits: NonEmptyTextList
    speech_style: SpeechStyle
    catchphrases: TextList = ()
    sources: SourceList = ()


class Relationship(KnowledgeModel):
    to: Slug
    type: RelationshipType = Field(strict=False)
    continuities: NonEmptySlugList
    description: NonEmptyText | None = None
    sources: SourceList = ()


class Character(KnowledgeModel):
    id: Slug
    name: NonEmptyText
    aliases: TextList = ()
    species: NonEmptyText
    versions: Annotated[tuple[CharacterVersion, ...], *_UNIQUE, Field(min_length=1)]
    relationships: Annotated[tuple[Relationship, ...], *_UNIQUE] = ()
    sources: SourceList = ()


class Location(KnowledgeModel):
    id: Slug
    name: NonEmptyText
    aliases: TextList = ()
    description: NonEmptyText
    continuities: NonEmptySlugList
    residents: SlugList = ()
    sources: SourceList = ()


class Artifact(KnowledgeModel):
    id: Slug
    name: NonEmptyText
    aliases: TextList = ()
    artifact_type: NonEmptyText
    description: NonEmptyText
    capabilities: TextList = ()
    limitations: TextList = ()
    continuities: NonEmptySlugList
    creators: SlugList = ()
    sources: SourceList = ()


class EntityType(StrEnum):
    CONTINUITY = "continuity"
    WORK = "work"
    EPISODE = "episode"
    CHARACTER = "character"
    LOCATION = "location"
    ARTIFACT = "artifact"


class EntityRef(KnowledgeModel):
    type: EntityType
    id: Slug


class KnowledgeSet(KnowledgeModel):
    """Entities checked together by the integrity rules."""

    continuities: tuple[Continuity, ...] = ()
    works: tuple[Work, ...] = ()
    episodes: tuple[Episode, ...] = ()
    characters: tuple[Character, ...] = ()
    locations: tuple[Location, ...] = ()
    artifacts: tuple[Artifact, ...] = ()


KnowledgeEntity = Continuity | Work | Episode | Character | Location | Artifact


class EntityKind(NamedTuple):
    model: type[KnowledgeModel]
    field: str


# The single registry of entity types; every other mapping derives from it.
ENTITY_KINDS: dict[EntityType, EntityKind] = {
    EntityType.CONTINUITY: EntityKind(Continuity, "continuities"),
    EntityType.WORK: EntityKind(Work, "works"),
    EntityType.EPISODE: EntityKind(Episode, "episodes"),
    EntityType.CHARACTER: EntityKind(Character, "characters"),
    EntityType.LOCATION: EntityKind(Location, "locations"),
    EntityType.ARTIFACT: EntityKind(Artifact, "artifacts"),
}
ENTITY_TYPES: dict[type[KnowledgeModel], EntityType] = {
    kind.model: entity_type for entity_type, kind in ENTITY_KINDS.items()
}
ENTITY_FIELDS: dict[EntityType, str] = {
    entity_type: kind.field for entity_type, kind in ENTITY_KINDS.items()
}


def entity_ref(entity: KnowledgeEntity) -> EntityRef:
    return EntityRef(type=ENTITY_TYPES[type(entity)], id=entity.id)


def entities_of(knowledge: KnowledgeSet) -> list[KnowledgeEntity]:
    """Every entity of the set, in the order of ``EntityType``."""

    return [
        entity
        for kind in EntityType
        for entity in getattr(knowledge, ENTITY_FIELDS[kind])
    ]


def references_of(knowledge: KnowledgeSet) -> dict[EntityType, set[str]]:
    """Ids of the entities that the entities of the set reference, by type."""

    refs: dict[EntityType, set[str]] = {kind: set() for kind in EntityType}
    for work in knowledge.works:
        refs[EntityType.CONTINUITY].add(work.continuity)
    for episode in knowledge.episodes:
        refs[EntityType.WORK].add(episode.work)
        refs[EntityType.CHARACTER].update(episode.characters)
        refs[EntityType.LOCATION].update(episode.locations)
        refs[EntityType.ARTIFACT].update(episode.artifacts)
    for character in knowledge.characters:
        for version in character.versions:
            refs[EntityType.CONTINUITY].update(version.continuities)
        for relationship in character.relationships:
            refs[EntityType.CHARACTER].add(relationship.to)
            refs[EntityType.CONTINUITY].update(relationship.continuities)
    for place in (*knowledge.locations, *knowledge.artifacts):
        refs[EntityType.CONTINUITY].update(place.continuities)
    for location in knowledge.locations:
        refs[EntityType.CHARACTER].update(location.residents)
    for artifact in knowledge.artifacts:
        refs[EntityType.CHARACTER].update(artifact.creators)
    return {kind: ids for kind, ids in refs.items() if ids}
