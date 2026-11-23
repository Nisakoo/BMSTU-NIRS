from __future__ import annotations

import logging
from pathlib import Path

from smeshariki_ai.rag.lore.analyzer import SimpleAnalyzer
from smeshariki_ai.rag.lore.index import InMemoryBm25Index
from smeshariki_ai.rag.lore.models import LoreQuery
from smeshariki_ai.rag.lore.services import LoadLore, SearchLore


def write_package(root: Path, *, text: str = "Возврат оплаты на карту.") -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "package.yaml").write_text("format_version: 1\n", encoding="utf-8")
    documents = root / "documents"
    documents.mkdir()
    (documents / "d01.yaml").write_text(
        f"id: d01\ntitle: Возврат\ntext: |\n  {text}\nsource: Синтетика\n",
        encoding="utf-8",
    )


async def test_load_and_search_use_the_same_index(tmp_path: Path) -> None:
    write_package(tmp_path, text="Возврат оплаты на карту. Возврат билета в кассе.")
    index = InMemoryBm25Index()
    loader = LoadLore(SimpleAnalyzer())

    report = await loader.load(tmp_path, index)
    result = await SearchLore(index, SimpleAnalyzer()).search(
        LoreQuery(text="возврат оплаты")
    )

    assert report.loaded is True
    assert report.summary is not None
    assert report.summary.document_count == 1
    assert report.summary.chunk_count == 1
    assert report.summary.term_count > 0
    assert result.hits
    assert result.hits[0].document_id == "d01"
    assert result.total == 1


async def test_invalid_package_does_not_replace_the_corpus(tmp_path: Path) -> None:
    index = InMemoryBm25Index()
    loader = LoadLore(SimpleAnalyzer())
    valid = tmp_path / "valid"
    write_package(valid)
    first = await loader.load(valid, index)

    invalid = tmp_path / "invalid"
    invalid.mkdir()
    (invalid / "package.yaml").write_text("format_version: 1\n", encoding="utf-8")
    (invalid / "documents").mkdir()
    (invalid / "documents" / "bad.yaml").write_text(
        "id: bad\ntext: |\n  Без заголовка.\n", encoding="utf-8"
    )

    report = await loader.load(invalid, index)

    assert first.loaded is True
    assert report.loaded is False
    assert report.issues
    assert await index.version() == first.summary.version


async def test_search_without_matches_is_empty(tmp_path: Path) -> None:
    write_package(tmp_path)
    index = InMemoryBm25Index()
    await LoadLore(SimpleAnalyzer()).load(tmp_path, index)

    result = await SearchLore(index, SimpleAnalyzer()).search(
        LoreQuery(text="бармалей")
    )

    assert result.hits == ()
    assert result.total == 0


async def test_load_uses_chunking_for_long_documents(tmp_path: Path) -> None:
    text = " ".join(f"Предложение {index} про Кроша." for index in range(100))
    write_package(tmp_path, text=text)
    index = InMemoryBm25Index()

    report = await LoadLore(SimpleAnalyzer()).load(tmp_path, index)

    assert report.loaded is True
    assert report.summary is not None
    assert report.summary.chunk_count > 1


async def test_lore_events_do_not_log_text(tmp_path: Path, caplog) -> None:
    write_package(tmp_path, text="Секретный текст про возврат оплаты.")
    index = InMemoryBm25Index()
    caplog.set_level(logging.INFO)

    await LoadLore(SimpleAnalyzer()).load(tmp_path, index)
    await SearchLore(index, SimpleAnalyzer()).search(
        LoreQuery(text="секретный возврат")
    )

    assert "lore.load.completed" in caplog.text
    assert "lore.search.completed" in caplog.text
    assert "Секретный" not in caplog.text
    assert "секретный" not in caplog.text
