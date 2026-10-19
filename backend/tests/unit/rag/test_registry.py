"""Every mapping keyed by entity type covers all types, so none is forgotten."""

from smeshariki_ai.rag.models import (
    ENTITY_FIELDS,
    ENTITY_KINDS,
    ENTITY_TYPES,
    EntityType,
    KnowledgeSet,
)
from smeshariki_ai.rag.package import ENTITY_DIRECTORIES, ENTITY_MODELS


def test_domain_registry_covers_every_entity_type() -> None:
    assert set(ENTITY_KINDS) == set(EntityType)
    assert set(ENTITY_TYPES.values()) == set(EntityType)
    assert set(ENTITY_FIELDS.values()) == set(KnowledgeSet.model_fields)


def test_package_adapter_covers_every_entity_type() -> None:
    assert set(ENTITY_MODELS) == set(EntityType)
    assert set(ENTITY_DIRECTORIES) == set(EntityType)


def test_postgres_mappers_cover_every_entity_type() -> None:
    from smeshariki_ai.rag.postgres_mappers import MAPPERS

    assert set(MAPPERS) == set(EntityType)
