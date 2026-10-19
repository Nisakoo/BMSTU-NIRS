"""Create the tables of RAG structured knowledge.

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "rag_artifacts",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("artifact_type", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column(
            "capabilities",
            postgresql.ARRAY(sa.Text()),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column(
            "limitations",
            postgresql.ARRAY(sa.Text()),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column(
            "sources",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "btrim(artifact_type) <> ''", name="rag_artifacts_artifact_type_not_blank"
        ),
        sa.CheckConstraint(
            "btrim(description) <> ''", name="rag_artifacts_description_not_blank"
        ),
        sa.CheckConstraint(
            "id ~ '^[a-z0-9]+(_[a-z0-9]+)*$'", name="rag_artifacts_id_format"
        ),
        sa.CheckConstraint(
            "jsonb_typeof(sources) = 'array'", name="rag_artifacts_sources_array"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "rag_characters",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("species", sa.Text(), nullable=False),
        sa.Column(
            "sources",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "btrim(species) <> ''", name="rag_characters_species_not_blank"
        ),
        sa.CheckConstraint(
            "id ~ '^[a-z0-9]+(_[a-z0-9]+)*$'", name="rag_characters_id_format"
        ),
        sa.CheckConstraint(
            "jsonb_typeof(sources) = 'array'", name="rag_characters_sources_array"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "rag_continuities",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("btrim(name) <> ''", name="rag_continuities_name_not_blank"),
        sa.CheckConstraint(
            "id ~ '^[a-z0-9]+(_[a-z0-9]+)*$'", name="rag_continuities_id_format"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "rag_loads",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("entity_count", sa.Integer(), nullable=True),
        sa.Column("counts", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.CheckConstraint(
            "finished_at >= started_at", name="rag_loads_finished_after_start"
        ),
        sa.CheckConstraint(
            "num_nulls(finished_at, duration_ms, entity_count, counts) IN (0, 4)",
            name="rag_loads_completion_consistent",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "rag_locations",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column(
            "sources",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "btrim(description) <> ''", name="rag_locations_description_not_blank"
        ),
        sa.CheckConstraint(
            "id ~ '^[a-z0-9]+(_[a-z0-9]+)*$'", name="rag_locations_id_format"
        ),
        sa.CheckConstraint(
            "jsonb_typeof(sources) = 'array'", name="rag_locations_sources_array"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "rag_artifact_continuities",
        sa.Column("artifact_id", sa.Text(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("continuity_id", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "position >= 0", name="rag_artifact_continuities_position_not_negative"
        ),
        sa.ForeignKeyConstraint(
            ["artifact_id"],
            ["rag_artifacts.id"],
            name="rag_artifact_continuities_artifact_id_fkey",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["continuity_id"],
            ["rag_continuities.id"],
            name="rag_artifact_continuities_continuity_id_fkey",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "artifact_id", "position", name="rag_artifact_continuities_pkey"
        ),
        sa.UniqueConstraint(
            "artifact_id", "continuity_id", name="rag_artifact_continuities_member_key"
        ),
    )
    op.create_index(
        "rag_artifact_continuities_continuity_id_idx",
        "rag_artifact_continuities",
        ["continuity_id"],
        unique=False,
    )
    op.create_table(
        "rag_artifact_creators",
        sa.Column("artifact_id", sa.Text(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("character_id", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "position >= 0", name="rag_artifact_creators_position_not_negative"
        ),
        sa.ForeignKeyConstraint(
            ["artifact_id"],
            ["rag_artifacts.id"],
            name="rag_artifact_creators_artifact_id_fkey",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["character_id"],
            ["rag_characters.id"],
            name="rag_artifact_creators_character_id_fkey",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "artifact_id", "position", name="rag_artifact_creators_pkey"
        ),
        sa.UniqueConstraint(
            "artifact_id", "character_id", name="rag_artifact_creators_member_key"
        ),
    )
    op.create_index(
        "rag_artifact_creators_character_id_idx",
        "rag_artifact_creators",
        ["character_id"],
        unique=False,
    )
    op.create_table(
        "rag_artifact_names",
        sa.Column("artifact_id", sa.Text(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("normalized", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "btrim(normalized) <> ''", name="rag_artifact_names_normalized_not_blank"
        ),
        sa.CheckConstraint(
            "btrim(value) <> ''", name="rag_artifact_names_value_not_blank"
        ),
        sa.CheckConstraint(
            "position >= 0", name="rag_artifact_names_position_not_negative"
        ),
        sa.ForeignKeyConstraint(
            ["artifact_id"],
            ["rag_artifacts.id"],
            name="rag_artifact_names_artifact_id_fkey",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "artifact_id", "position", name="rag_artifact_names_pkey"
        ),
    )
    op.create_index(
        "rag_artifact_names_normalized_idx",
        "rag_artifact_names",
        ["normalized"],
        unique=False,
    )
    op.create_table(
        "rag_character_names",
        sa.Column("character_id", sa.Text(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("normalized", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "btrim(normalized) <> ''", name="rag_character_names_normalized_not_blank"
        ),
        sa.CheckConstraint(
            "btrim(value) <> ''", name="rag_character_names_value_not_blank"
        ),
        sa.CheckConstraint(
            "position >= 0", name="rag_character_names_position_not_negative"
        ),
        sa.ForeignKeyConstraint(
            ["character_id"],
            ["rag_characters.id"],
            name="rag_character_names_character_id_fkey",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "character_id", "position", name="rag_character_names_pkey"
        ),
        sa.UniqueConstraint("normalized", name="rag_character_names_normalized_key"),
    )
    op.create_table(
        "rag_character_versions",
        sa.Column("character_id", sa.Text(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("age_group", sa.Text(), nullable=False),
        sa.Column("traits", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("speech_register", sa.Text(), nullable=False),
        sa.Column(
            "speech_markers",
            postgresql.ARRAY(sa.Text()),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column(
            "speech_constraints",
            postgresql.ARRAY(sa.Text()),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column(
            "catchphrases",
            postgresql.ARRAY(sa.Text()),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column(
            "sources",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "age_group IN ('child', 'teen', 'adult', 'elderly')",
            name="rag_character_versions_age_group_valid",
        ),
        sa.CheckConstraint(
            "btrim(speech_register) <> ''",
            name="rag_character_versions_speech_register_not_blank",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(sources) = 'array'",
            name="rag_character_versions_sources_array",
        ),
        sa.CheckConstraint(
            "cardinality(traits) >= 1", name="rag_character_versions_traits_not_empty"
        ),
        sa.CheckConstraint(
            "position >= 0", name="rag_character_versions_position_not_negative"
        ),
        sa.ForeignKeyConstraint(
            ["character_id"],
            ["rag_characters.id"],
            name="rag_character_versions_character_id_fkey",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "character_id", "position", name="rag_character_versions_pkey"
        ),
    )
    op.create_table(
        "rag_location_continuities",
        sa.Column("location_id", sa.Text(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("continuity_id", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "position >= 0", name="rag_location_continuities_position_not_negative"
        ),
        sa.ForeignKeyConstraint(
            ["continuity_id"],
            ["rag_continuities.id"],
            name="rag_location_continuities_continuity_id_fkey",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["location_id"],
            ["rag_locations.id"],
            name="rag_location_continuities_location_id_fkey",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "location_id", "position", name="rag_location_continuities_pkey"
        ),
        sa.UniqueConstraint(
            "location_id", "continuity_id", name="rag_location_continuities_member_key"
        ),
    )
    op.create_index(
        "rag_location_continuities_continuity_id_idx",
        "rag_location_continuities",
        ["continuity_id"],
        unique=False,
    )
    op.create_table(
        "rag_location_names",
        sa.Column("location_id", sa.Text(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("normalized", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "btrim(normalized) <> ''", name="rag_location_names_normalized_not_blank"
        ),
        sa.CheckConstraint(
            "btrim(value) <> ''", name="rag_location_names_value_not_blank"
        ),
        sa.CheckConstraint(
            "position >= 0", name="rag_location_names_position_not_negative"
        ),
        sa.ForeignKeyConstraint(
            ["location_id"],
            ["rag_locations.id"],
            name="rag_location_names_location_id_fkey",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "location_id", "position", name="rag_location_names_pkey"
        ),
    )
    op.create_index(
        "rag_location_names_normalized_idx",
        "rag_location_names",
        ["normalized"],
        unique=False,
    )
    op.create_table(
        "rag_location_residents",
        sa.Column("location_id", sa.Text(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("character_id", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "position >= 0", name="rag_location_residents_position_not_negative"
        ),
        sa.ForeignKeyConstraint(
            ["character_id"],
            ["rag_characters.id"],
            name="rag_location_residents_character_id_fkey",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["location_id"],
            ["rag_locations.id"],
            name="rag_location_residents_location_id_fkey",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "location_id", "position", name="rag_location_residents_pkey"
        ),
        sa.UniqueConstraint(
            "location_id", "character_id", name="rag_location_residents_member_key"
        ),
    )
    op.create_index(
        "rag_location_residents_character_id_idx",
        "rag_location_residents",
        ["character_id"],
        unique=False,
    )
    op.create_table(
        "rag_relationships",
        sa.Column("character_id", sa.Text(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("to_character_id", sa.Text(), nullable=False),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "sources",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "btrim(description) <> ''", name="rag_relationships_description_not_blank"
        ),
        sa.CheckConstraint(
            "jsonb_typeof(sources) = 'array'", name="rag_relationships_sources_array"
        ),
        sa.CheckConstraint(
            "type IN ('friendship', 'neighborhood', 'affection', 'mentor', 'guardian')",
            name="rag_relationships_type_valid",
        ),
        sa.CheckConstraint(
            "character_id <> to_character_id",
            name="rag_relationships_distinct_characters",
        ),
        sa.CheckConstraint(
            "position >= 0", name="rag_relationships_position_not_negative"
        ),
        sa.ForeignKeyConstraint(
            ["character_id"],
            ["rag_characters.id"],
            name="rag_relationships_character_id_fkey",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["to_character_id"],
            ["rag_characters.id"],
            name="rag_relationships_to_character_id_fkey",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "character_id", "position", name="rag_relationships_pkey"
        ),
    )
    op.create_index(
        "rag_relationships_to_character_id_idx",
        "rag_relationships",
        ["to_character_id"],
        unique=False,
    )
    op.create_table(
        "rag_revisions",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("load_id", sa.BigInteger(), nullable=False),
        sa.Column("entity_type", sa.Text(), nullable=False),
        sa.Column("entity_id", sa.Text(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("operation", sa.Text(), nullable=False),
        sa.Column("format_version", sa.Integer(), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "entity_id ~ '^[a-z0-9]+(_[a-z0-9]+)*$'",
            name="rag_revisions_entity_id_format",
        ),
        sa.CheckConstraint(
            "entity_type IN ('continuity', 'work', 'episode', 'character', 'location', 'artifact')",
            name="rag_revisions_entity_type_valid",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(payload) = 'object'", name="rag_revisions_payload_object"
        ),
        sa.CheckConstraint(
            "operation IN ('create', 'update', 'delete')",
            name="rag_revisions_operation_valid",
        ),
        sa.CheckConstraint("revision >= 1", name="rag_revisions_revision_positive"),
        sa.CheckConstraint(
            "format_version >= 1", name="rag_revisions_format_version_positive"
        ),
        sa.ForeignKeyConstraint(
            ["load_id"],
            ["rag_loads.id"],
            name="rag_revisions_load_id_fkey",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "entity_type", "entity_id", "revision", name="rag_revisions_entity_key"
        ),
    )
    op.create_index(
        "rag_revisions_load_id_idx", "rag_revisions", ["load_id"], unique=False
    )
    op.create_table(
        "rag_works",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("continuity_id", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("btrim(title) <> ''", name="rag_works_title_not_blank"),
        sa.CheckConstraint(
            "id ~ '^[a-z0-9]+(_[a-z0-9]+)*$'", name="rag_works_id_format"
        ),
        sa.CheckConstraint("kind IN ('series', 'film')", name="rag_works_kind_valid"),
        sa.ForeignKeyConstraint(
            ["continuity_id"],
            ["rag_continuities.id"],
            name="rag_works_continuity_id_fkey",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "rag_works_continuity_id_idx", "rag_works", ["continuity_id"], unique=False
    )
    op.create_table(
        "rag_character_version_continuities",
        sa.Column("character_id", sa.Text(), nullable=False),
        sa.Column("version_position", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("continuity_id", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "position >= 0",
            name="rag_character_version_continuities_position_not_negative",
        ),
        sa.ForeignKeyConstraint(
            ["character_id", "version_position"],
            ["rag_character_versions.character_id", "rag_character_versions.position"],
            name="rag_character_version_continuities_version_fkey",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["continuity_id"],
            ["rag_continuities.id"],
            name="rag_character_version_continuities_continuity_id_fkey",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "character_id",
            "continuity_id",
            name="rag_character_version_continuities_pkey",
        ),
        sa.UniqueConstraint(
            "character_id",
            "version_position",
            "position",
            name="rag_character_version_continuities_position_key",
        ),
    )
    op.create_index(
        "rag_character_version_continuities_continuity_id_idx",
        "rag_character_version_continuities",
        ["continuity_id"],
        unique=False,
    )
    op.create_table(
        "rag_episodes",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("work_id", sa.Text(), nullable=False),
        sa.Column("season", sa.Integer(), nullable=True),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("btrim(title) <> ''", name="rag_episodes_title_not_blank"),
        sa.CheckConstraint(
            "id ~ '^[a-z0-9]+(_[a-z0-9]+)*$'", name="rag_episodes_id_format"
        ),
        sa.CheckConstraint("number >= 1", name="rag_episodes_number_positive"),
        sa.CheckConstraint("season >= 1", name="rag_episodes_season_positive"),
        sa.ForeignKeyConstraint(
            ["work_id"],
            ["rag_works.id"],
            name="rag_episodes_work_id_fkey",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "work_id",
            "season",
            "number",
            name="rag_episodes_work_id_season_number_key",
            postgresql_nulls_not_distinct=True,
        ),
    )
    op.create_table(
        "rag_episode_artifacts",
        sa.Column("episode_id", sa.Text(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("artifact_id", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "position >= 0", name="rag_episode_artifacts_position_not_negative"
        ),
        sa.ForeignKeyConstraint(
            ["artifact_id"],
            ["rag_artifacts.id"],
            name="rag_episode_artifacts_artifact_id_fkey",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["episode_id"],
            ["rag_episodes.id"],
            name="rag_episode_artifacts_episode_id_fkey",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "episode_id", "position", name="rag_episode_artifacts_pkey"
        ),
        sa.UniqueConstraint(
            "episode_id", "artifact_id", name="rag_episode_artifacts_member_key"
        ),
    )
    op.create_index(
        "rag_episode_artifacts_artifact_id_idx",
        "rag_episode_artifacts",
        ["artifact_id"],
        unique=False,
    )
    op.create_table(
        "rag_episode_characters",
        sa.Column("episode_id", sa.Text(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("character_id", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "position >= 0", name="rag_episode_characters_position_not_negative"
        ),
        sa.ForeignKeyConstraint(
            ["character_id"],
            ["rag_characters.id"],
            name="rag_episode_characters_character_id_fkey",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["episode_id"],
            ["rag_episodes.id"],
            name="rag_episode_characters_episode_id_fkey",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "episode_id", "position", name="rag_episode_characters_pkey"
        ),
        sa.UniqueConstraint(
            "episode_id", "character_id", name="rag_episode_characters_member_key"
        ),
    )
    op.create_index(
        "rag_episode_characters_character_id_idx",
        "rag_episode_characters",
        ["character_id"],
        unique=False,
    )
    op.create_table(
        "rag_episode_locations",
        sa.Column("episode_id", sa.Text(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("location_id", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "position >= 0", name="rag_episode_locations_position_not_negative"
        ),
        sa.ForeignKeyConstraint(
            ["episode_id"],
            ["rag_episodes.id"],
            name="rag_episode_locations_episode_id_fkey",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["location_id"],
            ["rag_locations.id"],
            name="rag_episode_locations_location_id_fkey",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "episode_id", "position", name="rag_episode_locations_pkey"
        ),
        sa.UniqueConstraint(
            "episode_id", "location_id", name="rag_episode_locations_member_key"
        ),
    )
    op.create_index(
        "rag_episode_locations_location_id_idx",
        "rag_episode_locations",
        ["location_id"],
        unique=False,
    )
    op.create_table(
        "rag_relationship_continuities",
        sa.Column("character_id", sa.Text(), nullable=False),
        sa.Column("relationship_position", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("continuity_id", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "position >= 0", name="rag_relationship_continuities_position_not_negative"
        ),
        sa.ForeignKeyConstraint(
            ["character_id", "continuity_id"],
            [
                "rag_character_version_continuities.character_id",
                "rag_character_version_continuities.continuity_id",
            ],
            name="rag_relationship_continuities_version_fkey",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["character_id", "relationship_position"],
            ["rag_relationships.character_id", "rag_relationships.position"],
            name="rag_relationship_continuities_relationship_fkey",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "character_id",
            "relationship_position",
            "position",
            name="rag_relationship_continuities_pkey",
        ),
        sa.UniqueConstraint(
            "character_id",
            "relationship_position",
            "continuity_id",
            name="rag_relationship_continuities_continuity_key",
        ),
    )
    op.create_table(
        "rag_episode_interactions",
        sa.Column("episode_id", sa.Text(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("from_character_id", sa.Text(), nullable=False),
        sa.Column("to_character_id", sa.Text(), nullable=False),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column(
            "sources",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "btrim(description) <> ''",
            name="rag_episode_interactions_description_not_blank",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(sources) = 'array'",
            name="rag_episode_interactions_sources_array",
        ),
        sa.CheckConstraint(
            "type IN ('conflict', 'support', 'empathy')",
            name="rag_episode_interactions_type_valid",
        ),
        sa.CheckConstraint(
            "from_character_id <> to_character_id",
            name="rag_episode_interactions_distinct_characters",
        ),
        sa.CheckConstraint(
            "position >= 0", name="rag_episode_interactions_position_not_negative"
        ),
        sa.ForeignKeyConstraint(
            ["episode_id", "from_character_id"],
            [
                "rag_episode_characters.episode_id",
                "rag_episode_characters.character_id",
            ],
            name="rag_episode_interactions_from_fkey",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["episode_id", "to_character_id"],
            [
                "rag_episode_characters.episode_id",
                "rag_episode_characters.character_id",
            ],
            name="rag_episode_interactions_to_fkey",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["episode_id"],
            ["rag_episodes.id"],
            name="rag_episode_interactions_episode_id_fkey",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "episode_id", "position", name="rag_episode_interactions_pkey"
        ),
    )


def downgrade() -> None:
    op.drop_table("rag_episode_interactions")
    op.drop_table("rag_relationship_continuities")
    op.drop_index(
        "rag_episode_locations_location_id_idx", table_name="rag_episode_locations"
    )
    op.drop_table("rag_episode_locations")
    op.drop_index(
        "rag_episode_characters_character_id_idx", table_name="rag_episode_characters"
    )
    op.drop_table("rag_episode_characters")
    op.drop_index(
        "rag_episode_artifacts_artifact_id_idx", table_name="rag_episode_artifacts"
    )
    op.drop_table("rag_episode_artifacts")
    op.drop_table("rag_episodes")
    op.drop_index(
        "rag_character_version_continuities_continuity_id_idx",
        table_name="rag_character_version_continuities",
    )
    op.drop_table("rag_character_version_continuities")
    op.drop_index("rag_works_continuity_id_idx", table_name="rag_works")
    op.drop_table("rag_works")
    op.drop_index("rag_revisions_load_id_idx", table_name="rag_revisions")
    op.drop_table("rag_revisions")
    op.drop_index(
        "rag_relationships_to_character_id_idx", table_name="rag_relationships"
    )
    op.drop_table("rag_relationships")
    op.drop_index(
        "rag_location_residents_character_id_idx", table_name="rag_location_residents"
    )
    op.drop_table("rag_location_residents")
    op.drop_index("rag_location_names_normalized_idx", table_name="rag_location_names")
    op.drop_table("rag_location_names")
    op.drop_index(
        "rag_location_continuities_continuity_id_idx",
        table_name="rag_location_continuities",
    )
    op.drop_table("rag_location_continuities")
    op.drop_table("rag_character_versions")
    op.drop_table("rag_character_names")
    op.drop_index("rag_artifact_names_normalized_idx", table_name="rag_artifact_names")
    op.drop_table("rag_artifact_names")
    op.drop_index(
        "rag_artifact_creators_character_id_idx", table_name="rag_artifact_creators"
    )
    op.drop_table("rag_artifact_creators")
    op.drop_index(
        "rag_artifact_continuities_continuity_id_idx",
        table_name="rag_artifact_continuities",
    )
    op.drop_table("rag_artifact_continuities")
    op.drop_table("rag_locations")
    op.drop_table("rag_loads")
    op.drop_table("rag_continuities")
    op.drop_table("rag_characters")
    op.drop_table("rag_artifacts")
