"""Integrity rules of a knowledge set.

The rules do not know where the set comes from: a package check passes an
incomplete set, where a missing entity is an external reference, and a
database load passes the complete one, where it is an error. Entities are
visited in ``id`` order, so of two conflicting entities the later one gets the
violation. Every rule uses indexes built once and never compares entities
pairwise, which keeps the check linear in the size of the set.
"""

from collections import defaultdict
from collections.abc import Iterable, Sequence
from typing import Any

from smeshariki_ai.rag.models import (
    Artifact,
    Character,
    EntityRef,
    EntityType,
    Episode,
    InteractionType,
    KnowledgeModel,
    KnowledgeSet,
    Location,
    Relationship,
    RelationshipType,
    SourceRef,
    WorkKind,
    normalize_name,
)

_TYPE_ORDER = {kind: index for index, kind in enumerate(EntityType)}

# (first, second, type) -> owners and continuities of relationships seen so far.
_RelationshipIndex = dict[tuple[str, str, str], list[tuple[str, frozenset[str]]]]


class Violation(KnowledgeModel):
    entity: EntityRef
    path: str
    code: str
    message: str


class IntegrityReport(KnowledgeModel):
    violations: tuple[Violation, ...]
    external: tuple[EntityRef, ...]


def check_integrity(knowledge: KnowledgeSet, *, complete: bool) -> IntegrityReport:
    return _Checker(knowledge, complete).run()


def _by_id(items: Iterable[Any]) -> list[Any]:
    return sorted(items, key=lambda item: item.id)


def _pair_key(
    first: str, second: str, kind: RelationshipType | InteractionType
) -> tuple[str, str, str]:
    if kind.symmetric:
        first, second = sorted((first, second))
    return first, second, kind.value


class _Checker:
    def __init__(self, knowledge: KnowledgeSet, complete: bool) -> None:
        self._knowledge = knowledge
        self._complete = complete
        self._index: dict[EntityType, dict[str, Any]] = {
            EntityType.CONTINUITY: {c.id: c for c in knowledge.continuities},
            EntityType.WORK: {w.id: w for w in knowledge.works},
            EntityType.EPISODE: {e.id: e for e in knowledge.episodes},
            EntityType.CHARACTER: {c.id: c for c in knowledge.characters},
            EntityType.LOCATION: {loc.id: loc for loc in knowledge.locations},
            EntityType.ARTIFACT: {a.id: a for a in knowledge.artifacts},
        }
        # Continuities in which a character has a version.
        self._character_continuities = {
            character.id: frozenset(
                continuity
                for version in character.versions
                for continuity in version.continuities
            )
            for character in knowledge.characters
        }
        self._violations: list[Violation] = []
        self._external: set[EntityRef] = set()

    def run(self) -> IntegrityReport:
        for work in _by_id(self._knowledge.works):
            owner = EntityRef(type=EntityType.WORK, id=work.id)
            self._resolve(owner, "continuity", EntityType.CONTINUITY, work.continuity)
        self._check_episodes()
        self._check_characters()
        self._check_places_and_things()
        external = sorted(self._external, key=lambda r: (_TYPE_ORDER[r.type], r.id))
        return IntegrityReport(
            violations=tuple(self._violations), external=tuple(external)
        )

    def _violation(self, owner: EntityRef, path: str, code: str, message: str) -> None:
        self._violations.append(
            Violation(entity=owner, path=path, code=code, message=message)
        )

    def _resolve(
        self, owner: EntityRef, path: str, kind: EntityType, target: str
    ) -> bool:
        """Return whether ``target`` is in the set; record why it is not."""

        if target in self._index[kind]:
            return True
        ref = EntityRef(type=kind, id=target)
        if ref in self._knowledge.unverified:
            return False
        if self._complete:
            self._violation(
                owner,
                path,
                "unknown_reference",
                f"не найдена сущность типа «{kind.value}» с id «{target}»",
            )
        else:
            self._external.add(ref)
        return False

    def _resolve_all(
        self, owner: EntityRef, path: str, kind: EntityType, targets: Sequence[str]
    ) -> None:
        for position, target in enumerate(targets):
            self._resolve(owner, f"{path}[{position}]", kind, target)

    def _check_sources(
        self, owner: EntityRef, path: str, sources: Sequence[SourceRef]
    ) -> None:
        for position, source in enumerate(sources):
            if source.episode is not None:
                self._resolve(
                    owner,
                    f"{path}[{position}].episode",
                    EntityType.EPISODE,
                    source.episode,
                )

    def _check_episodes(self) -> None:
        numbers: dict[tuple[str, int | None, int], str] = {}
        film_episodes: dict[str, list[EntityRef]] = defaultdict(list)

        for episode in _by_id(self._knowledge.episodes):
            owner = EntityRef(type=EntityType.EPISODE, id=episode.id)
            continuity = None
            if self._resolve(owner, "work", EntityType.WORK, episode.work):
                work = self._index[EntityType.WORK][episode.work]
                continuity = work.continuity
                if work.kind is WorkKind.FILM:
                    film_episodes[work.id].append(owner)

            key = (episode.work, episode.season, episode.number)
            if key in numbers:
                self._violation(
                    owner,
                    "number",
                    "duplicate_episode_number",
                    f"номер уже занят эпизодом «{numbers[key]}»",
                )
            else:
                numbers[key] = episode.id

            self._check_participants(owner, episode, continuity)
            self._check_interactions(owner, episode)

        for episodes in film_episodes.values():
            if len(episodes) > 1:
                for owner in episodes:
                    self._violation(
                        owner,
                        "work",
                        "film_episode_count",
                        "у фильма может быть только один эпизод",
                    )

    def _check_participants(
        self, owner: EntityRef, episode: Episode, continuity: str | None
    ) -> None:
        for position, character in enumerate(episode.characters):
            path = f"characters[{position}]"
            if (
                self._resolve(owner, path, EntityType.CHARACTER, character)
                and continuity is not None
                and continuity not in self._character_continuities[character]
            ):
                self._violation(
                    owner,
                    path,
                    "continuity_mismatch",
                    f"у персонажа «{character}» нет версии в варианте канона "
                    f"«{continuity}»",
                )
        for field, kind in (
            ("locations", EntityType.LOCATION),
            ("artifacts", EntityType.ARTIFACT),
        ):
            for position, target in enumerate(getattr(episode, field)):
                path = f"{field}[{position}]"
                if (
                    self._resolve(owner, path, kind, target)
                    and continuity is not None
                    and continuity not in self._index[kind][target].continuities
                ):
                    self._violation(
                        owner,
                        path,
                        "continuity_mismatch",
                        f"«{target}» не существует в варианте канона «{continuity}»",
                    )

    def _check_interactions(self, owner: EntityRef, episode: Episode) -> None:
        participants = set(episode.characters)
        seen: dict[tuple[str, str, str], int] = {}

        for position, interaction in enumerate(episode.interactions):
            path = f"interactions[{position}]"
            self._check_sources(owner, f"{path}.sources", interaction.sources)
            if interaction.from_ == interaction.to:
                self._violation(
                    owner,
                    f"{path}.to",
                    "self_reference",
                    "взаимодействие должно связывать двух разных персонажей",
                )
                continue
            for field, character in (
                ("from", interaction.from_),
                ("to", interaction.to),
            ):
                if character not in participants:
                    self._violation(
                        owner,
                        f"{path}.{field}",
                        "interaction_participant",
                        f"персонаж «{character}» не указан в characters эпизода",
                    )
            key = _pair_key(interaction.from_, interaction.to, interaction.type)
            if key in seen:
                self._violation(
                    owner,
                    path,
                    "duplicate_interaction",
                    f"такое взаимодействие уже задано в interactions[{seen[key]}]",
                )
            else:
                seen[key] = position

    def _check_characters(self) -> None:
        names: dict[str, str] = {}
        relationships: _RelationshipIndex = defaultdict(list)

        for character in _by_id(self._knowledge.characters):
            owner = EntityRef(type=EntityType.CHARACTER, id=character.id)
            self._check_versions(owner, character)
            for position, relationship in enumerate(character.relationships):
                self._check_relationship(
                    owner, character.id, position, relationship, relationships
                )
            self._check_sources(owner, "sources", character.sources)
            self._check_character_names(owner, character, names)

    def _check_versions(self, owner: EntityRef, character: Character) -> None:
        version_of: dict[str, int] = {}
        for index, version in enumerate(character.versions):
            for position, continuity in enumerate(version.continuities):
                path = f"versions[{index}].continuities[{position}]"
                self._resolve(owner, path, EntityType.CONTINUITY, continuity)
                if continuity in version_of:
                    self._violation(
                        owner,
                        path,
                        "overlapping_versions",
                        f"вариант канона «{continuity}» уже задан в "
                        f"versions[{version_of[continuity]}]",
                    )
                else:
                    version_of[continuity] = index
            self._check_sources(owner, f"versions[{index}].sources", version.sources)

    def _check_relationship(
        self,
        owner: EntityRef,
        character_id: str,
        position: int,
        relationship: Relationship,
        seen: _RelationshipIndex,
    ) -> None:
        path = f"relationships[{position}]"
        self._check_sources(owner, f"{path}.sources", relationship.sources)
        if relationship.to == character_id:
            self._violation(
                owner,
                f"{path}.to",
                "self_reference",
                "отношение должно связывать двух разных персонажей",
            )
            return

        own = self._character_continuities[character_id]
        other = (
            self._character_continuities[relationship.to]
            if self._resolve(owner, f"{path}.to", EntityType.CHARACTER, relationship.to)
            else None
        )
        for index, continuity in enumerate(relationship.continuities):
            continuity_path = f"{path}.continuities[{index}]"
            self._resolve(owner, continuity_path, EntityType.CONTINUITY, continuity)
            if continuity not in own or (other is not None and continuity not in other):
                self._violation(
                    owner,
                    continuity_path,
                    "continuity_mismatch",
                    f"у обоих персонажей должна быть версия в варианте канона "
                    f"«{continuity}»",
                )

        continuities = frozenset(relationship.continuities)
        key = _pair_key(character_id, relationship.to, relationship.type)
        for other_owner, other_continuities in seen[key]:
            if continuities & other_continuities:
                self._violation(
                    owner,
                    path,
                    "duplicate_relationship",
                    f"такое отношение в тех же вариантах канона уже задано "
                    f"у персонажа «{other_owner}»",
                )
                break
        seen[key].append((character_id, continuities))

    def _check_character_names(
        self, owner: EntityRef, character: Character, names: dict[str, str]
    ) -> None:
        for path, name in self._names(character):
            key = normalize_name(name)
            holder = names.get(key)
            if holder is None:
                names[key] = character.id
            elif holder == character.id:
                self._violation(
                    owner,
                    path,
                    "duplicate_name",
                    f"«{name}» совпадает с другим именем или алиасом этого персонажа",
                )
            else:
                self._violation(
                    owner,
                    path,
                    "duplicate_name",
                    f"«{name}» уже используется персонажем «{holder}»",
                )

    @staticmethod
    def _names(entity: Character | Location | Artifact) -> list[tuple[str, str]]:
        return [("name", entity.name)] + [
            (f"aliases[{position}]", alias)
            for position, alias in enumerate(entity.aliases)
        ]

    def _check_places_and_things(self) -> None:
        for kind, entities, members in (
            (EntityType.LOCATION, self._knowledge.locations, "residents"),
            (EntityType.ARTIFACT, self._knowledge.artifacts, "creators"),
        ):
            names: dict[str, list[tuple[str, frozenset[str]]]] = defaultdict(list)
            for entity in _by_id(entities):
                owner = EntityRef(type=kind, id=entity.id)
                continuities = frozenset(entity.continuities)
                self._resolve_all(
                    owner, "continuities", EntityType.CONTINUITY, entity.continuities
                )
                self._check_members(owner, members, entity, continuities)
                self._check_sources(owner, "sources", entity.sources)
                self._check_scoped_names(owner, entity, continuities, names)

    def _check_members(
        self,
        owner: EntityRef,
        field: str,
        entity: Location | Artifact,
        continuities: frozenset[str],
    ) -> None:
        for position, character in enumerate(getattr(entity, field)):
            path = f"{field}[{position}]"
            if (
                self._resolve(owner, path, EntityType.CHARACTER, character)
                and not continuities & self._character_continuities[character]
            ):
                self._violation(
                    owner,
                    path,
                    "continuity_mismatch",
                    f"у персонажа «{character}» нет версии ни в одном варианте канона "
                    f"«{entity.id}»",
                )

    def _check_scoped_names(
        self,
        owner: EntityRef,
        entity: Location | Artifact,
        continuities: frozenset[str],
        names: dict[str, list[tuple[str, frozenset[str]]]],
    ) -> None:
        own: set[str] = set()
        for path, name in self._names(entity):
            key = normalize_name(name)
            if key in own:
                self._violation(
                    owner,
                    path,
                    "duplicate_name",
                    f"«{name}» совпадает с другим именем или алиасом этой сущности",
                )
                continue
            own.add(key)
            holder = next(
                (other for other, scope in names[key] if scope & continuities), None
            )
            if holder is not None:
                self._violation(
                    owner,
                    path,
                    "duplicate_name",
                    f"«{name}» уже используется «{holder}» в тех же вариантах канона",
                )
            names[key].append((entity.id, continuities))
