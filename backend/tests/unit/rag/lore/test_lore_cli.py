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


def test_lore_benchmark_context_prints_tool_path_metrics() -> None:
    output = io.StringIO()

    code = main(
        [
            "lore-benchmark",
            str(BENCHMARK_FIXTURE / "lore"),
            "--questions",
            str(BENCHMARK_FIXTURE / "questions.yaml"),
            "--answers",
            str(BENCHMARK_FIXTURE / "answers.json"),
            "--context",
        ],
        stdout=output,
    )

    assert code == 0
    assert "Context Recall:" in output.getvalue()
    assert "Context Any-Relevant:" in output.getvalue()
    assert "Context Found:" in output.getvalue()
    assert "Trap Passage Rate:" in output.getvalue()


def test_lore_benchmark_without_context_keeps_the_old_output() -> None:
    output = io.StringIO()

    code = main(
        [
            "lore-benchmark",
            str(BENCHMARK_FIXTURE / "lore"),
            "--questions",
            str(BENCHMARK_FIXTURE / "questions.yaml"),
            "--answers",
            str(BENCHMARK_FIXTURE / "answers.json"),
        ],
        stdout=output,
    )

    assert code == 0
    assert "Context Recall:" not in output.getvalue()
    assert "Trap Passage Rate:" not in output.getvalue()


def test_lore_benchmark_context_json_contains_context_fields() -> None:
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
            "--context",
        ],
        stdout=output,
    )

    report = json.loads(output.getvalue())
    assert code == 0
    assert report["context_recall"] is not None
    assert report["context_any_relevant"] is not None
    assert report["context_found_rate"] is not None
    assert report["trap_passage_rate"] is not None
    first = report["results"][0]
    assert first["context_status"] in ("found", "empty")
    assert isinstance(first["context_documents"], list)


URL = "https://youtu.be/9IsFUwqf188"


def write_package_with_url(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "package.yaml").write_text("format_version: 1\n", encoding="utf-8")
    (root / "documents").mkdir()
    path = root / "documents" / "d01.yaml"
    path.write_text(
        f"id: d01\ntitle: Возврат\ntext: |\n  {URL}\n  Возврат оплаты на карту.\n",
        encoding="utf-8",
    )
    return path


def test_lore_clean_defaults_to_dry_run(tmp_path: Path) -> None:
    path = write_package_with_url(tmp_path / "lore")
    before = path.read_text(encoding="utf-8")
    output = io.StringIO()

    code = main(["lore-clean", str(tmp_path / "lore")], stdout=output)

    assert code == 0
    assert "Будет очищено документов: 1" in output.getvalue()
    assert "--apply" in output.getvalue()
    assert path.read_text(encoding="utf-8") == before


def test_lore_clean_apply_rewrites_and_reports_backup(tmp_path: Path) -> None:
    path = write_package_with_url(tmp_path / "lore")
    output = io.StringIO()

    code = main(
        ["lore-clean", str(tmp_path / "lore"), "--apply"],
        stdout=output,
    )

    assert code == 0
    assert "Очищено документов: 1" in output.getvalue()
    assert "Резервная копия:" in output.getvalue()
    assert URL not in path.read_text(encoding="utf-8")


def test_lore_clean_apply_twice_reports_nothing_to_do(tmp_path: Path) -> None:
    write_package_with_url(tmp_path / "lore")
    main(["lore-clean", str(tmp_path / "lore"), "--apply"], stdout=io.StringIO())
    output = io.StringIO()

    code = main(["lore-clean", str(tmp_path / "lore"), "--apply"], stdout=output)

    assert code == 0
    assert "Чистить нечего" in output.getvalue()


def test_lore_clean_json_is_machine_readable(tmp_path: Path) -> None:
    write_package_with_url(tmp_path / "lore")
    output = io.StringIO()

    code = main(
        ["lore-clean", str(tmp_path / "lore"), "--format", "json"], stdout=output
    )

    report = json.loads(output.getvalue())
    assert code == 0
    assert report["applied"] is False
    assert report["document_count"] == 1
    assert report["changed_count"] == 1
    assert report["removed_lines"] == 1


def test_lore_clean_invalid_package_returns_one(tmp_path: Path) -> None:
    (tmp_path / "lore").mkdir()
    output = io.StringIO()

    code = main(["lore-clean", str(tmp_path / "lore")], stdout=output)

    assert code == 1
    assert "Чистка отменена" in output.getvalue()
