"""SQLAlchemy Core description of the ``rag_*`` tables of structured knowledge.

Each entity is an aggregate: a root table plus child tables owned by it.
Foreign keys inside an aggregate cascade; references between aggregates point
only at root tables and restrict deletion. Migration ``0003`` is the source of
truth for the database; a test checks that it matches this description.
"""

from collections.abc import Iterable
from enum import StrEnum

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKeyConstraint,
    Identity,
    Index,
    Integer,
    MetaData,
    PrimaryKeyConstraint,
    Table,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB

from smeshariki_ai.rag.models import (
    SLUG_PATTERN,
    AgeGroup,
    EntityType,
    InteractionType,
    RelationshipType,
    WorkKind,
)

metadata = MetaData()

REVISION_OPERATIONS = ("create", "update", "delete")


def _values(values: Iterable[StrEnum | str]) -> str:
    return ", ".join(f"'{value}'" for value in values)


def _one_of(
    table: str, column: str, values: Iterable[StrEnum | str]
) -> CheckConstraint:
    return CheckConstraint(
        f"{column} IN ({_values(values)})", name=f"{table}_{column}_valid"
    )


def _not_blank(table: str, column: str) -> CheckConstraint:
    return CheckConstraint(f"btrim({column}) <> ''", name=f"{table}_{column}_not_blank")


def _slug(table: str, column: str = "id") -> CheckConstraint:
    return CheckConstraint(
        f"{column} ~ '{SLUG_PATTERN}'", name=f"{table}_{column}_format"
    )


def _timestamps() -> list[Column]:
    return [
        Column(
            name,
            DateTime(timezone=True),
            nullable=False,
            server_default=func.now(),
        )
        for name in ("created_at", "updated_at")
    ]


def _sources(table: str) -> tuple[Column, CheckConstraint]:
    return (
        Column("sources", JSONB, nullable=False, server_default=text("'[]'::jsonb")),
        CheckConstraint(
            "jsonb_typeof(sources) = 'array'", name=f"{table}_sources_array"
        ),
    )


def _text_list(name: str) -> Column:
    return Column(name, ARRAY(Text), nullable=False, server_default=text("'{}'"))


def _position(table: str) -> tuple[Column, CheckConstraint]:
    return (
        Column("position", Integer, nullable=False),
        CheckConstraint("position >= 0", name=f"{table}_position_not_negative"),
    )


def _root(
    name: str, *columns: Column, constraints: Iterable = (), sources: bool = False
) -> Table:
    return Table(
        name,
        metadata,
        Column("id", Text, primary_key=True),
        *columns,
        *(_sources(name) if sources else ()),
        *_timestamps(),
        _slug(name),
        *constraints,
    )


def _names(owner: str, owner_column: str, *, unique: bool) -> Table:
    """Name at position 0 and aliases after it, with the normalized search key."""

    name = f"{owner}_names"
    table = Table(
        name,
        metadata,
        Column(owner_column, Text, nullable=False),
        *_position(name),
        Column("value", Text, nullable=False),
        Column("normalized", Text, nullable=False),
        PrimaryKeyConstraint(owner_column, "position", name=f"{name}_pkey"),
        ForeignKeyConstraint(
            [owner_column],
            [f"{owner}s.id"],
            ondelete="CASCADE",
            name=f"{name}_{owner_column}_fkey",
        ),
        _not_blank(name, "value"),
        _not_blank(name, "normalized"),
    )
    if unique:
        table.append_constraint(
            UniqueConstraint("normalized", name=f"{name}_normalized_key")
        )
    else:
        Index(f"{name}_normalized_idx", table.c.normalized)
    return table


def _members(
    owner: str, owner_column: str, member: str, member_column: str, suffix: str
) -> Table:
    """Ordered references from an aggregate to the roots of other aggregates."""

    name = f"{owner}_{suffix}"
    table = Table(
        name,
        metadata,
        Column(owner_column, Text, nullable=False),
        *_position(name),
        Column(member_column, Text, nullable=False),
        PrimaryKeyConstraint(owner_column, "position", name=f"{name}_pkey"),
        UniqueConstraint(owner_column, member_column, name=f"{name}_member_key"),
        ForeignKeyConstraint(
            [owner_column],
            [f"{owner}s.id"],
            ondelete="CASCADE",
            name=f"{name}_{owner_column}_fkey",
        ),
        ForeignKeyConstraint(
            [member_column],
            [f"{member}.id"],
            ondelete="RESTRICT",
            name=f"{name}_{member_column}_fkey",
        ),
    )
    Index(f"{name}_{member_column}_idx", table.c[member_column])
    return table


continuities = _root(
    "rag_continuities",
    Column("name", Text, nullable=False),
    constraints=[_not_blank("rag_continuities", "name")],
)

works = _root(
    "rag_works",
    Column("title", Text, nullable=False),
    Column("kind", Text, nullable=False),
    Column("continuity_id", Text, nullable=False),
    constraints=[
        _not_blank("rag_works", "title"),
        _one_of("rag_works", "kind", WorkKind),
        ForeignKeyConstraint(
            ["continuity_id"],
            ["rag_continuities.id"],
            ondelete="RESTRICT",
            name="rag_works_continuity_id_fkey",
        ),
    ],
)
Index("rag_works_continuity_id_idx", works.c.continuity_id)

episodes = _root(
    "rag_episodes",
    Column("work_id", Text, nullable=False),
    Column("season", Integer, nullable=True),
    Column("number", Integer, nullable=False),
    Column("title", Text, nullable=False),
    constraints=[
        _not_blank("rag_episodes", "title"),
        CheckConstraint("season >= 1", name="rag_episodes_season_positive"),
        CheckConstraint("number >= 1", name="rag_episodes_number_positive"),
        UniqueConstraint(
            "work_id",
            "season",
            "number",
            name="rag_episodes_work_id_season_number_key",
            postgresql_nulls_not_distinct=True,
        ),
        ForeignKeyConstraint(
            ["work_id"],
            ["rag_works.id"],
            ondelete="RESTRICT",
            name="rag_episodes_work_id_fkey",
        ),
    ],
)

characters = _root(
    "rag_characters",
    Column("species", Text, nullable=False),
    constraints=[_not_blank("rag_characters", "species")],
    sources=True,
)

locations = _root(
    "rag_locations",
    Column("description", Text, nullable=False),
    constraints=[_not_blank("rag_locations", "description")],
    sources=True,
)

artifacts = _root(
    "rag_artifacts",
    Column("artifact_type", Text, nullable=False),
    Column("description", Text, nullable=False),
    _text_list("capabilities"),
    _text_list("limitations"),
    constraints=[
        _not_blank("rag_artifacts", "artifact_type"),
        _not_blank("rag_artifacts", "description"),
    ],
    sources=True,
)

episode_characters = _members(
    "rag_episode", "episode_id", "rag_characters", "character_id", "characters"
)
episode_locations = _members(
    "rag_episode", "episode_id", "rag_locations", "location_id", "locations"
)
episode_artifacts = _members(
    "rag_episode", "episode_id", "rag_artifacts", "artifact_id", "artifacts"
)

episode_interactions = Table(
    "rag_episode_interactions",
    metadata,
    Column("episode_id", Text, nullable=False),
    *_position("rag_episode_interactions"),
    Column("from_character_id", Text, nullable=False),
    Column("to_character_id", Text, nullable=False),
    Column("type", Text, nullable=False),
    Column("description", Text, nullable=False),
    *_sources("rag_episode_interactions"),
    PrimaryKeyConstraint(
        "episode_id", "position", name="rag_episode_interactions_pkey"
    ),
    ForeignKeyConstraint(
        ["episode_id"],
        ["rag_episodes.id"],
        ondelete="CASCADE",
        name="rag_episode_interactions_episode_id_fkey",
    ),
    # Both participants must take part in the same episode.
    ForeignKeyConstraint(
        ["episode_id", "from_character_id"],
        ["rag_episode_characters.episode_id", "rag_episode_characters.character_id"],
        ondelete="CASCADE",
        name="rag_episode_interactions_from_fkey",
    ),
    ForeignKeyConstraint(
        ["episode_id", "to_character_id"],
        ["rag_episode_characters.episode_id", "rag_episode_characters.character_id"],
        ondelete="CASCADE",
        name="rag_episode_interactions_to_fkey",
    ),
    CheckConstraint(
        "from_character_id <> to_character_id",
        name="rag_episode_interactions_distinct_characters",
    ),
    _one_of("rag_episode_interactions", "type", InteractionType),
    _not_blank("rag_episode_interactions", "description"),
)

character_names = _names("rag_character", "character_id", unique=True)
location_names = _names("rag_location", "location_id", unique=False)
artifact_names = _names("rag_artifact", "artifact_id", unique=False)

character_versions = Table(
    "rag_character_versions",
    metadata,
    Column("character_id", Text, nullable=False),
    *_position("rag_character_versions"),
    Column("age_group", Text, nullable=False),
    Column("traits", ARRAY(Text), nullable=False),
    Column("speech_register", Text, nullable=False),
    _text_list("speech_markers"),
    _text_list("speech_constraints"),
    _text_list("catchphrases"),
    *_sources("rag_character_versions"),
    PrimaryKeyConstraint(
        "character_id", "position", name="rag_character_versions_pkey"
    ),
    ForeignKeyConstraint(
        ["character_id"],
        ["rag_characters.id"],
        ondelete="CASCADE",
        name="rag_character_versions_character_id_fkey",
    ),
    _one_of("rag_character_versions", "age_group", AgeGroup),
    CheckConstraint(
        "cardinality(traits) >= 1", name="rag_character_versions_traits_not_empty"
    ),
    _not_blank("rag_character_versions", "speech_register"),
)

# The key (character, continuity) allows at most one version per continuity.
character_version_continuities = Table(
    "rag_character_version_continuities",
    metadata,
    Column("character_id", Text, nullable=False),
    Column("version_position", Integer, nullable=False),
    *_position("rag_character_version_continuities"),
    Column("continuity_id", Text, nullable=False),
    PrimaryKeyConstraint(
        "character_id",
        "continuity_id",
        name="rag_character_version_continuities_pkey",
    ),
    UniqueConstraint(
        "character_id",
        "version_position",
        "position",
        name="rag_character_version_continuities_position_key",
    ),
    ForeignKeyConstraint(
        ["character_id", "version_position"],
        ["rag_character_versions.character_id", "rag_character_versions.position"],
        ondelete="CASCADE",
        name="rag_character_version_continuities_version_fkey",
    ),
    ForeignKeyConstraint(
        ["continuity_id"],
        ["rag_continuities.id"],
        ondelete="RESTRICT",
        name="rag_character_version_continuities_continuity_id_fkey",
    ),
)
Index(
    "rag_character_version_continuities_continuity_id_idx",
    character_version_continuities.c.continuity_id,
)

relationships = Table(
    "rag_relationships",
    metadata,
    Column("character_id", Text, nullable=False),
    *_position("rag_relationships"),
    Column("to_character_id", Text, nullable=False),
    Column("type", Text, nullable=False),
    Column("description", Text, nullable=True),
    *_sources("rag_relationships"),
    PrimaryKeyConstraint("character_id", "position", name="rag_relationships_pkey"),
    ForeignKeyConstraint(
        ["character_id"],
        ["rag_characters.id"],
        ondelete="CASCADE",
        name="rag_relationships_character_id_fkey",
    ),
    ForeignKeyConstraint(
        ["to_character_id"],
        ["rag_characters.id"],
        ondelete="RESTRICT",
        name="rag_relationships_to_character_id_fkey",
    ),
    CheckConstraint(
        "character_id <> to_character_id",
        name="rag_relationships_distinct_characters",
    ),
    _one_of("rag_relationships", "type", RelationshipType),
    _not_blank("rag_relationships", "description"),
)
Index("rag_relationships_to_character_id_idx", relationships.c.to_character_id)

# A relationship holds only where its owner has a version.
relationship_continuities = Table(
    "rag_relationship_continuities",
    metadata,
    Column("character_id", Text, nullable=False),
    Column("relationship_position", Integer, nullable=False),
    *_position("rag_relationship_continuities"),
    Column("continuity_id", Text, nullable=False),
    PrimaryKeyConstraint(
        "character_id",
        "relationship_position",
        "position",
        name="rag_relationship_continuities_pkey",
    ),
    UniqueConstraint(
        "character_id",
        "relationship_position",
        "continuity_id",
        name="rag_relationship_continuities_continuity_key",
    ),
    ForeignKeyConstraint(
        ["character_id", "relationship_position"],
        ["rag_relationships.character_id", "rag_relationships.position"],
        ondelete="CASCADE",
        name="rag_relationship_continuities_relationship_fkey",
    ),
    ForeignKeyConstraint(
        ["character_id", "continuity_id"],
        [
            "rag_character_version_continuities.character_id",
            "rag_character_version_continuities.continuity_id",
        ],
        ondelete="CASCADE",
        name="rag_relationship_continuities_version_fkey",
    ),
)

location_continuities = _members(
    "rag_location", "location_id", "rag_continuities", "continuity_id", "continuities"
)
location_residents = _members(
    "rag_location", "location_id", "rag_characters", "character_id", "residents"
)
artifact_continuities = _members(
    "rag_artifact", "artifact_id", "rag_continuities", "continuity_id", "continuities"
)
artifact_creators = _members(
    "rag_artifact", "artifact_id", "rag_characters", "character_id", "creators"
)

loads = Table(
    "rag_loads",
    metadata,
    Column("id", BigInteger, Identity(always=True), primary_key=True),
    Column("started_at", DateTime(timezone=True), nullable=False),
    Column("finished_at", DateTime(timezone=True), nullable=True),
    Column("duration_ms", Integer, nullable=True),
    Column("entity_count", Integer, nullable=True),
    Column("counts", JSONB, nullable=True),
    # A load is recorded first and completed at the end of the same transaction.
    CheckConstraint(
        "num_nulls(finished_at, duration_ms, entity_count, counts) IN (0, 4)",
        name="rag_loads_completion_consistent",
    ),
    CheckConstraint("finished_at >= started_at", name="rag_loads_finished_after_start"),
)

revisions = Table(
    "rag_revisions",
    metadata,
    Column("id", BigInteger, Identity(always=True), primary_key=True),
    Column("load_id", BigInteger, nullable=False),
    Column("entity_type", Text, nullable=False),
    Column("entity_id", Text, nullable=False),
    Column("revision", Integer, nullable=False),
    Column("operation", Text, nullable=False),
    Column("format_version", Integer, nullable=False),
    Column("payload", JSONB, nullable=False),
    Column(
        "recorded_at",
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    ),
    ForeignKeyConstraint(
        ["load_id"],
        ["rag_loads.id"],
        ondelete="RESTRICT",
        name="rag_revisions_load_id_fkey",
    ),
    UniqueConstraint(
        "entity_type", "entity_id", "revision", name="rag_revisions_entity_key"
    ),
    _one_of("rag_revisions", "entity_type", EntityType),
    _one_of("rag_revisions", "operation", REVISION_OPERATIONS),
    _slug("rag_revisions", "entity_id"),
    CheckConstraint("revision >= 1", name="rag_revisions_revision_positive"),
    CheckConstraint(
        "format_version >= 1", name="rag_revisions_format_version_positive"
    ),
    CheckConstraint(
        "jsonb_typeof(payload) = 'object'", name="rag_revisions_payload_object"
    ),
)
Index("rag_revisions_load_id_idx", revisions.c.load_id)
