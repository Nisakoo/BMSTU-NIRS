from __future__ import annotations

import io
import json
from contextlib import asynccontextmanager
from pathlib import Path

from smeshariki_ai.rag.cli import main
from smeshariki_ai.rag.lore.index import InMemoryBm25Index

BENCHMARK_FIXTURE = Path(__file__).parents[3] / "fixtures" / "lore_benchmark"


def write_package(root: Path, *, text: str = "Возврат оплаты на карту.") -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "package.yaml").write_text("format_version: 1\n", encoding="utf-8")
    (root / "documents").mkdir()
    (root / "documents" / "d01.yaml").write_text(
        f"id: d01\ntitle: Возврат\ntext: |\n  {text}\n",
        encoding="utf-8",
    )


@asynccontextmanager
async def index_context(index: InMemoryBm25Index):
    yield index


def test_lore_check_prints_a_valid_report(tmp_path: Path) -> None:
    write_package(tmp_path)
    output = io.StringIO()

    code = main(["lore-check", str(tmp_path)], stdout=output)

    assert code == 0
    assert "Пакет лора валиден." in output.getvalue()
    assert "Документов: 1" in output.getvalue()


def test_lore_check_returns_one_for_an_invalid_package(tmp_path: Path) -> None:
    (tmp_path / "package.yaml").write_text("format_version: 1\n", encoding="utf-8")
    output = io.StringIO()

    code = main(["lore-check", str(tmp_path)], stdout=output)

    assert code == 1
    assert "Ошибок:" in output.getvalue()


def test_lore_check_json_is_machine_readable(tmp_path: Path) -> None:
    write_package(tmp_path)
    output = io.StringIO()

    code = main(["lore-check", str(tmp_path), "--format", "json"], stdout=output)

    report = json.loads(output.getvalue())
    assert code == 0
    assert report["valid"] is True
    assert report["document_count"] == 1


def test_lore_load_and_search_share_the_index(tmp_path: Path) -> None:
    write_package(tmp_path)
    index = InMemoryBm25Index()
    load_output = io.StringIO()
    search_output = io.StringIO()

    load_code = main(
        ["lore-load", str(tmp_path)],
        stdout=load_output,
        lore_store=lambda: index_context(index),
    )
    search_code = main(
        ["lore-search", "возврат оплаты"],
        stdout=search_output,
        lore_index=lambda: index_context(index),
    )

    assert load_code == 0
    assert "Загрузка 1 выполнена." in load_output.getvalue()
    assert search_code == 0
    assert "Возврат" in search_output.getvalue()


def test_lore_search_prints_nothing_found(tmp_path: Path) -> None:
    write_package(tmp_path)
    index = InMemoryBm25Index()
    output = io.StringIO()

    main(
        ["lore-load", str(tmp_path)],
        stdout=io.StringIO(),
        lore_store=lambda: index_context(index),
    )
    code = main(
        ["lore-search", "бармалей"],
        stdout=output,
        lore_index=lambda: index_context(index),
    )

    assert code == 0
    assert "Ничего не найдено." in output.getvalue()


def test_lore_search_json_returns_hits(tmp_path: Path) -> None:
    write_package(tmp_path)
    index = InMemoryBm25Index()
    output = io.StringIO()

    main(
        ["lore-load", str(tmp_path)],
        stdout=io.StringIO(),
        lore_store=lambda: index_context(index),
    )
    code = main(
        ["lore-search", "возврат", "--format", "json"],
        stdout=output,
        lore_index=lambda: index_context(index),
    )

    result = json.loads(output.getvalue())
    assert code == 0
    assert result["hits"][0]["document_id"] == "d01"


def test_lore_benchmark_uses_prepared_answers() -> None:
    output = io.StringIO()

    code = main(
        [
            "lore-benchmark",
            str(BENCHMARK_FIXTURE / "lore"),
            "--questions",
            str(BENCHMARK_FIXTURE / "questions.yaml"),
            "--answers",
            str(BENCHMARK_FIXTURE / "answers.json"),
            "--k",
            "5",
        ],
        stdout=output,
    )

    assert code == 0
    assert "Recall@5:" in output.getvalue()
    assert "Correct Rejection Rate: 1.000" in output.getvalue()


def test_lore_benchmark_json_is_machine_readable() -> None:
    output = io.StringIO()

    code = main(
        [
            "lore-benchmark",
            str(BENCHMARK_FIXTURE / "lore"),
            "--questions",
            str(BENCHMARK_FIXTURE / "questions.yaml"),
            "--answers",
            str(BENCHMARK_FIXTURE / "answers.json"),
            "--format",
            "json",
        ],
        stdout=output,
    )

    report = json.loads(output.getvalue())
    assert code == 0
    assert report["document_count"] == 30
    assert report["normal_count"] == 10
    assert report["trap_count"] == 5
    assert report["correct_rejection_rate"] == 1.0
