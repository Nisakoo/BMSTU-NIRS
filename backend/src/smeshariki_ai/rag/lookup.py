"""Use case of exact knowledge lookup for the agent.

A lookup normalizes the requested name, reads the matching entities through
``KnowledgeReader`` and turns them into compact cards: references are shown by
name instead of slug and sources are left out, since the model writes stories
and does not cite them.
"""

import logging
import time
from typing import Annotated, Literal

from pydantic import Field

from smeshariki_ai.observability import log_event, utc_now
from smeshariki_ai.rag.models import (
    AgeGroup,
    Artifact,
    Character,
    EntityType,
    Episode,
    InteractionType,
    KnowledgeModel,
    Location,
    RelationshipType,
    normalize_name,
)
from smeshariki_ai.rag.ports import FoundKnowledge, KnowledgeReader, KnowledgeStoreError

logger = logging.getLogger(__name__)

LOOKUP_LIMIT = 10
NOT_FOUND_MESSAGE = (
    "В базе знаний нет героя, места, предмета или эпизода с таким именем или "
    "названием. Не выдавай придуманные факты за канонические."
)
UNAVAILABLE_MESSAGE = (
    "База знаний сейчас недоступна. Не выдавай придуманные факты за канонические."
)

LookupStatus = Literal["found", "not_found", "unavailable"]


class SpeechStyleCard(KnowledgeModel):
    # A field named ``register`` shadows a ``BaseModel`` attribute.
    register_: str = Field(alias="register")
    markers: tuple[str, ...]
    constraints: tuple[str, ...]


class CharacterVersionCard(KnowledgeModel):
    continuities: tuple[str, ...]
    age_group: AgeGroup
    traits: tuple[str, ...]
    speech_style: SpeechStyleCard
    catchphrases: tuple[str, ...]


class RelationshipCard(KnowledgeModel):
    to: str
    type: RelationshipType
    continuities: tuple[str, ...]
    description: str | None


class CharacterCard(KnowledgeModel):
    type: Literal["character"] = "character"
    id: str
    name: str
    aliases: tuple[str, ...]
    species: str
    versions: tuple[CharacterVersionCard, ...]
    relationships: tuple[RelationshipCard, ...]


class LocationCard(KnowledgeModel):
    type: Literal["location"] = "location"
    id: str
    name: str
    aliases: tuple[str, ...]
    description: str
    continuities: tuple[str, ...]
    residents: tuple[str, ...]


class ArtifactCard(KnowledgeModel):
    type: Literal["artifact"] = "artifact"
    id: str
    name: str
    aliases: tuple[str, ...]
    artifact_type: str
    description: str
    capabilities: tuple[str, ...]
    limitations: tuple[str, ...]
    continuities: tuple[str, ...]
    creators: tuple[str, ...]


class InteractionCard(KnowledgeModel):
    from_: str = Field(alias="from")
    to: str
    type: InteractionType
    description: str


class EpisodeCard(KnowledgeModel):
    type: Literal["episode"] = "episode"
    id: str
    title: str
    work: str
    continuity: str | None
    season: int | None
    number: int
    characters: tuple[str, ...]
    locations: tuple[str, ...]
    artifacts: tuple[str, ...]
    interactions: tuple[InteractionCard, ...]


Card = Annotated[
    CharacterCard | LocationCard | ArtifactCard | EpisodeCard,
    Field(discriminator="type"),
]


class LookupResult(KnowledgeModel):
    status: LookupStatus
    # Number of matching entities; at most ``LOOKUP_LIMIT`` of them are shown.
    total: int = Field(ge=0)
    truncated: bool
    matches: tuple[Card, ...]
    message: str | None = None


class _Cards:
    """Builds the cards of found entities, showing references by name."""

    def __init__(self, found: FoundKnowledge) -> None:
        self._found = found
        self._names = found.names
        self._works = {work.id: work for work in found.entities.works}

    def _name(self, kind: EntityType, entity_id: str) -> str:
        # A missing name falls back to the slug rather than failing the lookup.
        return self._names.get(kind, {}).get(entity_id, entity_id)

    def _all(self, kind: EntityType, ids: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(self._name(kind, entity_id) for entity_id in ids)

    def _continuities(self, ids: tuple[str, ...]) -> tuple[str, ...]:
        return self._all(EntityType.CONTINUITY, ids)

    def character(self, character: Character) -> CharacterCard:
        return CharacterCard(
            id=character.id,
            name=character.name,
            aliases=character.aliases,
            species=character.species,
            versions=tuple(
                CharacterVersionCard(
                    continuities=self._continuities(version.continuities),
                    age_group=version.age_group,
                    traits=version.traits,
                    speech_style=SpeechStyleCard.model_validate(
                        {
                            "register": version.speech_style.register_,
                            "markers": version.speech_style.markers,
                            "constraints": version.speech_style.constraints,
                        }
                    ),
                    catchphrases=version.catchphrases,
                )
                for version in character.versions
            ),
            relationships=tuple(
                RelationshipCard(
                    to=self._name(EntityType.CHARACTER, relationship.to),
                    type=relationship.type,
                    continuities=self._continuities(relationship.continuities),
                    description=relationship.description,
                )
                for relationship in character.relationships
            ),
        )

    def location(self, location: Location) -> LocationCard:
        return LocationCard(
            id=location.id,
            name=location.name,
            aliases=location.aliases,
            description=location.description,
            continuities=self._continuities(location.continuities),
            residents=self._all(EntityType.CHARACTER, location.residents),
        )

    def artifact(self, artifact: Artifact) -> ArtifactCard:
        return ArtifactCard(
            id=artifact.id,
            name=artifact.name,
            aliases=artifact.aliases,
            artifact_type=artifact.artifact_type,
            description=artifact.description,
            capabilities=artifact.capabilities,
            limitations=artifact.limitations,
            continuities=self._continuities(artifact.continuities),
            creators=self._all(EntityType.CHARACTER, artifact.creators),
        )

    def episode(self, episode: Episode) -> EpisodeCard:
        work = self._works.get(episode.work)
        return EpisodeCard(
            id=episode.id,
            title=episode.title,
            work=self._name(EntityType.WORK, episode.work),
            continuity=None
            if work is None
            else self._name(EntityType.CONTINUITY, work.continuity),
            season=episode.season,
            number=episode.number,
            characters=self._all(EntityType.CHARACTER, episode.characters),
            locations=self._all(EntityType.LOCATION, episode.locations),
            artifacts=self._all(EntityType.ARTIFACT, episode.artifacts),
            interactions=tuple(
                InteractionCard.model_validate(
                    {
                        "from": self._name(EntityType.CHARACTER, item.from_),
                        "to": self._name(EntityType.CHARACTER, item.to),
                        "type": item.type,
                        "description": item.description,
                    }
                )
                for item in episode.interactions
            ),
        )

    def all(self) -> list[Card]:
        """Cards by type; the reader returns each type ordered by ``id``."""

        entities = self._found.entities
        return [
            *(self.character(item) for item in entities.characters),
            *(self.location(item) for item in entities.locations),
            *(self.artifact(item) for item in entities.artifacts),
            *(self.episode(item) for item in entities.episodes),
        ]


class KnowledgeLookup:
    def __init__(self, reader: KnowledgeReader, *, limit: int = LOOKUP_LIMIT) -> None:
        self._reader = reader
        self._limit = limit

    async def lookup(self, name: str) -> LookupResult:
        started_at = utc_now()
        started = time.monotonic()
        error_type = reason = None
        try:
            result = await self._lookup(normalize_name(name))
        except KnowledgeStoreError as error:
            error_type = type(error).__name__
            result = _unavailable()
        else:
            if result.status == "unavailable":
                reason = "not_loaded"
        log_event(
            logger,
            logging.WARNING if error_type else logging.INFO,
            "rag.lookup.completed",
            started_at=started_at,
            duration_ms=round((time.monotonic() - started) * 1000, 3),
            outcome=result.status,
            match_count=result.total,
            error_type=error_type,
            reason=reason,
        )
        return result

    async def _lookup(self, key: str) -> LookupResult:
        found = await self._reader.find(key)
        cards = _Cards(found).all()
        if cards:
            return LookupResult(
                status="found",
                total=len(cards),
                truncated=len(cards) > self._limit,
                matches=tuple(cards[: self._limit]),
            )
        if not await self._reader.has_knowledge():
            return _unavailable()
        return LookupResult(
            status="not_found",
            total=0,
            truncated=False,
            matches=(),
            message=NOT_FOUND_MESSAGE,
        )


def _unavailable() -> LookupResult:
    return LookupResult(
        status="unavailable",
        total=0,
        truncated=False,
        matches=(),
        message=UNAVAILABLE_MESSAGE,
    )
