from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncEngine

from smeshariki_ai.agent.models import ToolCall
from smeshariki_ai.agent.tools import ToolRegistry
from smeshariki_ai.rag.lore.analyzer import SimpleAnalyzer
from smeshariki_ai.rag.lore.bm25 import Bm25Params
from smeshariki_ai.rag.lore.context import LoreContextBuilder
from smeshariki_ai.rag.lore.index import InMemoryBm25Index
from smeshariki_ai.rag.lore.models import LoreQuery
from smeshariki_ai.rag.lore.ports import LoreSchemaNotReadyError
from smeshariki_ai.rag.lore.postgres import (
    PostgresBm25Index,
    PostgresLoreDocumentStore,
    PostgresLoreStore,
)
from smeshariki_ai.rag.lore.services import LoadLore, SearchLore
from smeshariki_ai.rag.lore.tools import SearchLoreTool


def write_package(root: Path, documents: dict[str, str]) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "package.yaml").write_text("format_version: 1\n", encoding="utf-8")
    documents_dir = root / "documents"
    documents_dir.mkdir()
    for name, content in documents.items():
        (documents_dir / f"{name}.yaml").write_text(
            "id: " + name + "\n"
            "title: " + name.upper() + "\n"
            "text: |\n"
            f"  {content}\n"
            "source: Синтетика\n",
            encoding="utf-8",
        )


async def test_postgres_search_ranks_and_returns_metadata(
    engine: AsyncEngine, tmp_path: Path
) -> None:
    write_package(
        tmp_path,
        {
            "a": "Возврат оплаты на карту.",
            "b": "Статус оплаты в приложении.",
            "c": "Возврат билета через кассу.",
        },
    )
    analyzer = SimpleAnalyzer()
    store = PostgresLoreStore(engine)
    index = PostgresBm25Index(engine)

    report = await LoadLore(analyzer).load(tmp_path, store)
    result = await SearchLore(index, analyzer).search(
        LoreQuery(text="возврат оплаты", top_k=2)
    )

    assert report.loaded is True
    assert report.summary is not None
    assert report.summary.document_count == 3
    assert report.summary.chunk_count == 3
    assert [hit.document_id for hit in result.hits] == ["a", "b"]
    assert result.hits[0].title == "A"
    assert result.hits[0].source == "Синтетика"
    assert result.hits[0].rank == 1

    documents = await PostgresLoreDocumentStore(engine).documents()
    assert [document.id for document in documents] == ["a", "b", "c"]


async def test_search_lore_tool_uses_postgres_and_returns_compact_context(
    engine: AsyncEngine, tmp_path: Path
) -> None:
    write_package(
        tmp_path,
        {
            "a": "Крош и Ёжик поссорились из-за игры.",
            "b": "Друзья нашли общее дело и помирились.",
            "c": "Нюша и Бараш спорят о музыке.",
        },
    )
    analyzer = SimpleAnalyzer()
    await LoadLore(analyzer).load(tmp_path, PostgresLoreStore(engine))
    registry = ToolRegistry(
        (
            SearchLoreTool(
                SearchLore(PostgresBm25Index(engine), analyzer),
                LoreContextBuilder(),
            ),
        )
    )

    result = await registry.execute(
        ToolCall(id="call-1", name="search_lore", arguments={"query": "Крош Ёжик"})
    )

    assert result.error is None
    assert result.output["status"] == "found"
    assert 1 <= len(result.output["passages"]) <= 3
    assert set(result.output["passages"][0]) == {"title", "source", "text"}
    assert result.output["passages"][0]["title"] == "A"


async def test_postgres_and_in_memory_have_the_same_order(
    engine: AsyncEngine, tmp_path: Path
) -> None:
    write_package(
        tmp_path,
        {
            "a": "Крош и Ёжик строят ракету. Пин помогает друзьям.",
            "b": "Нюша и Бараш спорят о музыке.",
            "c": "Копатыч варит мёд и вспоминает лето.",
        },
    )
    analyzer = SimpleAnalyzer()
    postgres = PostgresBm25Index(engine)
    memory = InMemoryBm25Index()
    loader = LoadLore(analyzer)
    await loader.load(tmp_path, PostgresLoreStore(engine))
    await loader.load(tmp_path, memory)

    for query in ("крош ракета", "нюша музыка", "мед лето", "нет совпадений"):
        expected = await SearchLore(memory, analyzer).search(
            LoreQuery(text=query, top_k=5)
        )
        actual = await SearchLore(postgres, analyzer).search(
            LoreQuery(text=query, top_k=5)
        )
        assert [(hit.document_id, hit.position) for hit in actual.hits] == [
            (hit.document_id, hit.position) for hit in expected.hits
        ]


async def test_postgres_load_replaces_the_previous_corpus(
    engine: AsyncEngine, tmp_path: Path
) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    write_package(first, {"a": "Старый текст про возврат."})
    write_package(second, {"b": "Новый текст про космос."})
    analyzer = SimpleAnalyzer()
    store = PostgresLoreStore(engine)
    loader = LoadLore(analyzer)

    first_report = await loader.load(first, store)
    second_report = await loader.load(second, store)
    old = await SearchLore(PostgresBm25Index(engine), analyzer).search(
        LoreQuery(text="возврат")
    )
    new = await SearchLore(PostgresBm25Index(engine), analyzer).search(
        LoreQuery(text="космос")
    )

    assert first_report.loaded and second_report.loaded
    assert second_report.summary.version == first_report.summary.version + 1
    assert old.hits == ()
    assert [hit.document_id for hit in new.hits] == ["b"]


async def test_search_uses_a_fixed_number_of_queries(
    engine: AsyncEngine, tmp_path: Path
) -> None:
    write_package(tmp_path, {"a": "Возврат оплаты на карту."})
    analyzer = SimpleAnalyzer()
    await LoadLore(analyzer).load(tmp_path, PostgresLoreStore(engine))

    statements: list[str] = []

    def before_cursor_execute(
        connection: object,
        cursor: object,
        statement: str,
        parameters: object,
        context: object,
        executemany: bool,
    ) -> None:
        statements.append(statement)

    event.listen(engine.sync_engine, "before_cursor_execute", before_cursor_execute)
    try:
        await SearchLore(PostgresBm25Index(engine), analyzer).search(
            LoreQuery(text="возврат оплаты", top_k=5)
        )
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", before_cursor_execute)

    assert len(statements) <= 2


async def test_missing_tables_are_reported_as_schema_not_ready(
    engine: AsyncEngine,
) -> None:
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "DROP TABLE rag_lore_postings, rag_lore_terms, "
                "rag_lore_chunks, rag_lore_documents, rag_lore_stats, "
                "rag_lore_loads CASCADE"
            )
        )

    with pytest.raises(LoreSchemaNotReadyError):
        await PostgresBm25Index(engine).search(["слово"], 5, Bm25Params())
