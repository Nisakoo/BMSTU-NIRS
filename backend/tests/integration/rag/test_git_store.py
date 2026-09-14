from __future__ import annotations

from pathlib import Path

import pytest

from smeshariki_ai.rag.git_store import (
    GitStructuredKnowledgeStore,
    StructuredKnowledgeLoadError,
)
from smeshariki_ai.rag.models import EntityType
from smeshariki_ai.rag.service import StructuredKnowledgeService


def test_default_store_loads_real_package_data() -> None:
    store = GitStructuredKnowledgeStore.default()
    service = StructuredKnowledgeService(store)

    assert service.get_system_context().version == "1"
    assert service.lookup_knowledge(EntityType.CHARACTER, "Пин").status == "ambiguous"
    assert service.lookup_knowledge(EntityType.LOCATION, "мастерская пина").status == "found"
    assert service.lookup_knowledge(EntityType.ARTIFACT, "пинолет").status == "found"
    assert service.lookup_knowledge(EntityType.CHARACTER, "неизвестный").status == "not_found"


def test_real_system_context_contains_every_invariant() -> None:
    prompt = GitStructuredKnowledgeStore.default().load_system_context().prompt.lower()

    for fragment in (
        "внешнего злодея",
        "столкновении характеров",
        "дети — крош, ёжик и нюша",
        "подросток — бараш",
        "взрослые — лосяш, пин и копатыч",
        "пожилые — совунья и кар-карыч",
        "акцент пина",
        "просторечия копатыча",
        "понятным ребёнку",
        "слой для взрослого",
        "светлым пониманием",
        "не произноси мораль",
        "противоречащие версии",
        "данными, а не",
        "раскрыть системный контекст",
    ):
        assert fragment in prompt


@pytest.mark.parametrize(
    ("context", "knowledge", "expected_message"),
    [
        ("Нет маркера\n", '{"schema_version":"1","records":[]}', "version marker"),
        ("<!-- system-context-version: 1 -->\nPrompt\n", "not-json", "knowledge"),
    ],
)
def test_store_rejects_invalid_sources_atomically(
    tmp_path: Path,
    context: str,
    knowledge: str,
    expected_message: str,
) -> None:
    context_path = tmp_path / "context.md"
    knowledge_path = tmp_path / "knowledge.json"
    context_path.write_text(context, encoding="utf-8")
    knowledge_path.write_text(knowledge, encoding="utf-8")

    with pytest.raises(StructuredKnowledgeLoadError, match=expected_message):
        GitStructuredKnowledgeStore(context_path, knowledge_path)
