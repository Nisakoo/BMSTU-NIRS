from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from smeshariki_ai.rag.cli import main
from smeshariki_ai.rag.knowledge_benchmark import (
    KnowledgeBenchmarkError,
    KnowledgeBenchmarkQuestion,
    KnowledgeBenchmarkRunner,
    KnowledgeBenchmarkSet,
    read_knowledge_questions,
)
from smeshariki_ai.rag.lookup import KnowledgeLookup
from smeshariki_ai.rag.memory import InMemoryKnowledgeStore

PACKAGE_YAML = {
    "package.yaml": "format_version: 1\n",
    "characters/krosh.yaml": (
        "id: krosh\n"
        "name: Крош\n"
        "aliases: [Кроша]\n"
        "species: кролик\n"
        "versions:\n"
        "- continuities: [classic]\n"
        "  age_group: adult\n"
        "  traits: [весёлый]\n"
        "  interests: []\n"
        "  speech_style: {register: neutral, markers: [], constraints: []}\n"
        "  catchphrases: []\n"
        "relationships: []\n"
    ),
    "continuities/classic.yaml": "id: classic\nname: Классика\n",
}


def write_package(root: Path) -> None:
    for relative, text in PACKAGE_YAML.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


def questions_path(tmp_path: Path) -> Path:
    path = tmp_path / "questions.yaml"
    path.write_text(
        "questions:\n"
        "- id: q_exact\n"
        "  query: Крош\n"
        "  kind: exact\n"
        "  expected: krosh\n"
        "- id: q_alias\n"
        "  query: Кроша\n"
        "  kind: alias\n"
        "  expected: krosh\n"
        "- id: q_typo\n"
        "  query: Крш\n"
        "  kind: typo\n"
        "  expected: krosh\n"
        "- id: q_negative\n"
        "  query: Карлсон\n"
        "  kind: negative\n",
        encoding="utf-8",
    )
    return path


async def test_benchmark_scores_exact_alias_typo_and_negative(
    tmp_path: Path,
) -> None:
    package = tmp_path / "knowledge"
    write_package(package)
    questions = read_knowledge_questions(questions_path(tmp_path))
    runner = KnowledgeBenchmarkRunner(KnowledgeLookup(InMemoryKnowledgeStore()))

    report = await runner.run(package, questions)

    assert report.question_count == 4
    assert report.exact_count == 2
    assert report.typo_count == 1
    assert report.negative_count == 1
    assert report.exact_match_rate == 1.0
    assert report.false_positive_rate == 0.0
    results = {item.question_id: item for item in report.results}
    assert results["q_exact"].correct is True
    assert results["q_alias"].correct is True
    assert results["q_negative"].correct is True


async def test_benchmark_reports_a_wrong_expectation(tmp_path: Path) -> None:
    package = tmp_path / "knowledge"
    write_package(package)
    questions = KnowledgeBenchmarkSet(
        questions=(
            KnowledgeBenchmarkQuestion(
                id="q1", query="Крош", kind="exact", expected="pin"
            ),
        )
    )
    runner = KnowledgeBenchmarkRunner(KnowledgeLookup(InMemoryKnowledgeStore()))

    report = await runner.run(package, questions)

    assert report.exact_match_rate == 0.0
    assert report.results[0].status == "found"
    assert report.results[0].correct is False


async def test_invalid_package_is_a_safe_error(tmp_path: Path) -> None:
    package = tmp_path / "knowledge"
    package.mkdir()
    questions = read_knowledge_questions(questions_path(tmp_path))
    runner = KnowledgeBenchmarkRunner(KnowledgeLookup(InMemoryKnowledgeStore()))

    with pytest.raises(KnowledgeBenchmarkError):
        await runner.run(package, questions)


def test_invalid_questions_file_is_a_safe_error(tmp_path: Path) -> None:
    path = tmp_path / "questions.yaml"
    path.write_text("not: a benchmark\n", encoding="utf-8")

    with pytest.raises(KnowledgeBenchmarkError):
        read_knowledge_questions(path)


def test_knowledge_benchmark_cli_prints_metrics(tmp_path: Path) -> None:
    package = tmp_path / "knowledge"
    write_package(package)
    questions = questions_path(tmp_path)
    output = io.StringIO()

    code = main(
        ["knowledge-benchmark", str(package), "--questions", str(questions)],
        stdout=output,
    )

    assert code == 0
    assert "Accuracy:" in output.getvalue()
    assert "Exact match rate: 1.000" in output.getvalue()


def test_knowledge_benchmark_cli_json_is_machine_readable(tmp_path: Path) -> None:
    package = tmp_path / "knowledge"
    write_package(package)
    questions = questions_path(tmp_path)
    output = io.StringIO()

    code = main(
        [
            "knowledge-benchmark",
            str(package),
            "--questions",
            str(questions),
            "--format",
            "json",
        ],
        stdout=output,
    )

    report = json.loads(output.getvalue())
    assert code == 0
    assert report["question_count"] == 4
    assert report["exact_match_rate"] == 1.0
