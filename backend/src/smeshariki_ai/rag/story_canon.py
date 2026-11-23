"""Compact story profile projected from the structured canon.

The full ``lookup_knowledge`` card is for factual questions. This read model
keeps only what constrains a character in a story: age, traits, speech,
catchphrases and the type of a relationship. Free-text relationship
descriptions, sources, locations and artifacts never leave the canon.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Sequence
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from smeshariki_ai.observability import log_event, utc_now
from smeshariki_ai.rag.models import (
    AgeGroup,
    Character,
    CharacterVersion,
    EntityType,
    RelationshipType,
    normalize_name,
)
from smeshariki_ai.rag.ports import KnowledgeReader, KnowledgeStoreError

logger = logging.getLogger(__name__)

StoryName = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)
]

NOT_FOUND_MESSAGE = (
    "В каноне нет подходящего профиля для запрошенных героев. Продолжай по идее "
    "пользователя и не придумывай канонические детали."
)
NO_VERSION_MESSAGE = (
    "У запрошенных героев нет версии в выбранном варианте канона. Не подставляй "
    "версию другого канона."
)
UNAVAILABLE_MESSAGE = (
    "Структурированный канон сейчас недоступен. Не выдавай придуманные факты за "
    "канонические."
)

StoryStatus = Literal["found", "not_found", "unavailable"]


class StoryModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class StorySpeechStyle(StoryModel):
    register_: str = Field(alias="register")
    markers: tuple[str, ...] = ()
    constraints: tuple[str, ...] = ()


class StoryRelationship(StoryModel):
    to: str
    type: RelationshipType


class StoryCharacter(StoryModel):
    id: str
    name: str
    species: str
    continuity: str
    age_group: AgeGroup
    traits: tuple[str, ...]
    speech_style: StorySpeechStyle
    catchphrases: tuple[str, ...]
    relationships: tuple[StoryRelationship, ...] = ()


class StoryCanonResult(StoryModel):
    status: StoryStatus
    characters: tuple[StoryCharacter, ...] = ()
    message: str | None = None


class StoryCanonLookup:
    """Read model for story generation; it does not change the canon."""

    def __init__(
        self,
        reader: KnowledgeReader,
        *,
        default_continuity: str = "classic",
        limit: int = 3,
    ) -> None:
        if limit <= 0:
            raise ValueError("limit must be positive")
        self._reader = reader
        self._default_continuity = default_continuity
        self._limit = limit

    async def lookup(
        self,
        names: Sequence[str],
        continuity: str | None = None,
    ) -> StoryCanonResult:
        clean = tuple(dict.fromkeys(name.strip() for name in names if name.strip()))
        if not clean or len(clean) > self._limit:
            raise ValueError("expected one to three non-empty names")

        target = continuity or self._default_continuity
        started_at = utc_now()
        started = time.monotonic()
        collected: dict[str, StoryCharacter] = {}
        found_character = False
        found_version = False

        try:
            for name in clean:
                found = await self._reader.find(normalize_name(name))
                if not found.entities.characters:
                    continue
                found_character = True
                for character in found.entities.characters:
                    version = next(
                        (
                            item
                            for item in character.versions
                            if target in item.continuities
                        ),
                        None,
                    )
                    if version is None:
                        continue
                    found_version = True
                    if character.id in collected:
                        continue
                    collected[character.id] = self._project(
                        character,
                        version,
                        target,
                        found.names,
                    )
                    if len(collected) >= self._limit:
                        break
                if len(collected) >= self._limit:
                    break
        except KnowledgeStoreError as error:
            log_event(
                logger,
                logging.WARNING,
                "rag.story_canon.completed",
                started_at=started_at,
                duration_ms=round((time.monotonic() - started) * 1000, 3),
                outcome="unavailable",
                entity_count=0,
                error_type=type(error).__name__,
            )
            return StoryCanonResult(status="unavailable", message=UNAVAILABLE_MESSAGE)

        if collected:
            result = StoryCanonResult(
                status="found",
                characters=tuple(collected.values()),
            )
            reason = None
        elif not found_character:
            result = await self._no_characters()
            reason = "not_found" if result.status == "not_found" else "not_loaded"
        elif not found_version:
            result = StoryCanonResult(status="not_found", message=NO_VERSION_MESSAGE)
            reason = "no_version"
        else:
            result = StoryCanonResult(status="not_found", message=NOT_FOUND_MESSAGE)
            reason = "not_found"

        log_event(
            logger,
            logging.INFO,
            "rag.story_canon.completed",
            started_at=started_at,
            duration_ms=round((time.monotonic() - started) * 1000, 3),
            outcome=result.status,
            entity_count=len(result.characters),
            reason=reason,
        )
        return result

    async def _no_characters(self) -> StoryCanonResult:
        try:
            has_knowledge = await self._reader.has_knowledge()
        except KnowledgeStoreError:
            return StoryCanonResult(status="unavailable", message=UNAVAILABLE_MESSAGE)
        if not has_knowledge:
            return StoryCanonResult(status="unavailable", message=UNAVAILABLE_MESSAGE)
        return StoryCanonResult(status="not_found", message=NOT_FOUND_MESSAGE)

    def _project(
        self,
        character: Character,
        version: CharacterVersion,
        continuity: str,
        names: dict[EntityType, dict[str, str]],
    ) -> StoryCharacter:
        speaker = version.speech_style
        relationships: list[StoryRelationship] = []
        seen: set[tuple[str, str]] = set()
        character_names = names.get(EntityType.CHARACTER, {})
        for relationship in character.relationships:
            if continuity not in relationship.continuities:
                continue
            to = character_names.get(relationship.to, relationship.to)
            key = (to, relationship.type.value)
            if key in seen:
                continue
            seen.add(key)
            relationships.append(StoryRelationship(to=to, type=relationship.type))
        return StoryCharacter(
            id=character.id,
            name=character.name,
            species=character.species,
            continuity=continuity,
            age_group=version.age_group,
            traits=version.traits,
            speech_style=StorySpeechStyle(
                register=speaker.register_,
                markers=speaker.markers,
                constraints=speaker.constraints,
            ),
            catchphrases=version.catchphrases,
            relationships=tuple(relationships),
        )


__all__ = [
    "NOT_FOUND_MESSAGE",
    "NO_VERSION_MESSAGE",
    "UNAVAILABLE_MESSAGE",
    "StoryCanonLookup",
    "StoryCanonResult",
    "StoryCharacter",
    "StoryName",
    "StoryRelationship",
    "StorySpeechStyle",
]
