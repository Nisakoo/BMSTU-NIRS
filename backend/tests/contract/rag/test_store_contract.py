from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from smeshariki_ai.rag.git_store import GitStructuredKnowledgeStore
from smeshariki_ai.rag.in_memory import InMemoryStructuredKnowledgeStore
from smeshariki_ai.rag.models import (
    AgeGroup,
    CharacterProfile,
    EntityType,
    KnowledgeCatalog,
    SourceRef,
    SpeechStyle,
    SystemContext,
)
from smeshariki_ai.rag.ports import StructuredKnowledgeStorePort


def character(record_id: str, variants: tuple[str, ...]) -> CharacterProfile:
    return CharacterProfile(
        entity_type=EntityType.CHARACTER,
        id=record_id,
        name="Пин",
        aliases=(f"alias-{record_id}",),
        canon_variants=variants,
        source_refs=(
            SourceRef(
                source_id=record_id,
                source_version="1",
                locator="characters.json:1",
                checksum="sha256:fixture",
            ),
        ),
        species="пингвин",
        age_group=AgeGroup.ADULT,
        traits=("изобретательный",),
        speech_style=SpeechStyle(
            register="разговорный",
            markers=("акцент",),
            constraints=("разборчиво",),
        ),
    )


@pytest.fixture(params=("memory", "file"))
def store(request: pytest.FixtureRequest, tmp_path: Path) -> Iterator[StructuredKnowledgeStorePort]:
    context = SystemContext(version="1", prompt="Инвариантные правила")
    catalog = KnowledgeCatalog(
        schema_version="1",
        records=(
            character("pin", ("classic",)),
            character("pin_movie", ("movie",)),
        ),
    )
    if request.param == "memory":
        yield InMemoryStructuredKnowledgeStore(
            system_context=context,
            records=catalog.records,
        )
        return

    context_path = tmp_path / "system_context.md"
    knowledge_path = tmp_path / "knowledge.json"
    context_path.write_text(
        "<!-- system-context-version: 1 -->\nИнвариантные правила\n",
        encoding="utf-8",
    )
    knowledge_path.write_text(catalog.model_dump_json(indent=2), encoding="utf-8")
    yield GitStructuredKnowledgeStore(context_path, knowledge_path)


def test_store_contract_loads_context_and_records(
    store: StructuredKnowledgeStorePort,
) -> None:
    assert store.load_system_context().version == "1"
    assert len(store.load_records()) == 2


def test_store_contract_finds_exact_records_with_canon_or_filter(
    store: StructuredKnowledgeStorePort,
) -> None:
    all_matches = store.find(EntityType.CHARACTER, "пин", ())
    movie = store.find(EntityType.CHARACTER, "пин", ("movie", "unknown"))

    assert [record.id for record in all_matches] == ["pin", "pin_movie"]
    assert [record.id for record in movie] == ["pin_movie"]
