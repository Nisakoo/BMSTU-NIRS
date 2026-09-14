from __future__ import annotations

from enum import Enum
import re
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator


NonEmptyStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]

_FILE_LINE = re.compile(r"^[^\s:]+:[1-9]\d*$")
_EPISODE_TIMECODE = re.compile(r"^[^\s:]+:(?:(?:\d{2}):)?[0-5]\d:[0-5]\d$")


def normalize_lookup_key(value: str) -> str:
    return value.strip().lower().replace("ё", "е")


class StrictModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        validate_by_alias=True,
        validate_by_name=True,
        serialize_by_alias=True,
    )


class EntityType(str, Enum):
    CHARACTER = "character"
    LOCATION = "location"
    ARTIFACT = "artifact"


class AgeGroup(str, Enum):
    CHILD = "child"
    TEEN = "teen"
    ADULT = "adult"
    ELDERLY = "elderly"


class SystemContext(StrictModel):
    version: NonEmptyStr
    prompt: NonEmptyStr


class SourceRef(StrictModel):
    source_id: NonEmptyStr
    source_version: NonEmptyStr
    locator: NonEmptyStr
    checksum: NonEmptyStr

    @field_validator("locator")
    @classmethod
    def validate_locator(cls, value: str) -> str:
        if not (_FILE_LINE.fullmatch(value) or _EPISODE_TIMECODE.fullmatch(value)):
            raise ValueError(
                "locator must be filename:line or episode_id:MM:SS/HH:MM:SS"
            )
        return value


class SpeechStyle(StrictModel):
    register_: NonEmptyStr = Field(alias="register")
    markers: tuple[NonEmptyStr, ...]
    constraints: tuple[NonEmptyStr, ...]


class KnowledgeRecordBase(StrictModel):
    id: NonEmptyStr
    name: NonEmptyStr
    aliases: tuple[NonEmptyStr, ...]
    canon_variants: tuple[NonEmptyStr, ...]
    source_refs: tuple[SourceRef, ...]


class CharacterProfile(KnowledgeRecordBase):
    entity_type: Literal[EntityType.CHARACTER]
    species: NonEmptyStr
    age_group: AgeGroup
    traits: tuple[NonEmptyStr, ...]
    speech_style: SpeechStyle


class LocationProfile(KnowledgeRecordBase):
    entity_type: Literal[EntityType.LOCATION]
    description: NonEmptyStr
    resident_ids: tuple[NonEmptyStr, ...]


class ArtifactProfile(KnowledgeRecordBase):
    entity_type: Literal[EntityType.ARTIFACT]
    artifact_type: NonEmptyStr
    description: NonEmptyStr
    capabilities: tuple[NonEmptyStr, ...]
    limitations: tuple[NonEmptyStr, ...]
    creator_ids: tuple[NonEmptyStr, ...]


KnowledgeRecord = Annotated[
    CharacterProfile | LocationProfile | ArtifactProfile,
    Field(discriminator="entity_type"),
]


class KnowledgeRef(StrictModel):
    entity_type: EntityType
    id: NonEmptyStr
    name: NonEmptyStr
    canon_variants: tuple[NonEmptyStr, ...]


class KnowledgeLookupRequest(StrictModel):
    entity_type: EntityType
    key: NonEmptyStr
    canon_variants: tuple[NonEmptyStr, ...] = ()


class KnowledgeFound(StrictModel):
    status: Literal["found"] = "found"
    entity: KnowledgeRecord


class KnowledgeNotFound(StrictModel):
    status: Literal["not_found"] = "not_found"
    entity_type: EntityType
    key: NonEmptyStr
    canon_variants: tuple[NonEmptyStr, ...]


class KnowledgeAmbiguous(StrictModel):
    status: Literal["ambiguous"] = "ambiguous"
    entity_type: EntityType
    key: NonEmptyStr
    canon_variants: tuple[NonEmptyStr, ...]
    candidates: tuple[KnowledgeRef, ...]


KnowledgeLookupResult = Annotated[
    KnowledgeFound | KnowledgeNotFound | KnowledgeAmbiguous,
    Field(discriminator="status"),
]


class KnowledgeCatalog(StrictModel):
    schema_version: NonEmptyStr
    records: tuple[KnowledgeRecord, ...]

    @model_validator(mode="after")
    def validate_catalog(self) -> KnowledgeCatalog:
        seen_ids: set[tuple[EntityType, str]] = set()
        seen_aliases: dict[str, tuple[EntityType, str]] = {}

        for record in self.records:
            record_key = (EntityType(record.entity_type), record.id)
            if record_key in seen_ids:
                raise ValueError(
                    f"duplicate knowledge id for {record.entity_type}: {record.id}"
                )
            seen_ids.add(record_key)

            for alias in record.aliases:
                normalized_alias = normalize_lookup_key(alias)
                owner = seen_aliases.get(normalized_alias)
                if owner is not None:
                    raise ValueError(
                        "duplicate normalized alias "
                        f"{normalized_alias!r} for {owner} and {record_key}"
                    )
                seen_aliases[normalized_alias] = record_key

        character_ids = {
            record.id
            for record in self.records
            if record.entity_type == EntityType.CHARACTER
        }
        for record in self.records:
            references: tuple[str, ...] = ()
            if isinstance(record, LocationProfile):
                references = record.resident_ids
            elif isinstance(record, ArtifactProfile):
                references = record.creator_ids
            unknown = sorted(set(references) - character_ids)
            if unknown:
                raise ValueError(
                    f"unknown character id referenced by {record.id}: {unknown}"
                )

        return self
