from __future__ import annotations

import json
from collections.abc import AsyncIterator, Sequence
from pathlib import Path

import pytest

from smeshariki_ai.agent import LLMProvider, LLMResponse, LLMTextDelta, Message
from smeshariki_ai.rag.lore.analyzer import MorphAnalyzer
from smeshariki_ai.rag.lore.benchmark import (
    BenchmarkError,
    BenchmarkQuestion,
    BenchmarkRunner,
    StaticAnswerer,
    read_benchmark_questions,
)
from smeshariki_ai.rag.lore.benchmark_llm import LiteLLMAnswerer
from smeshariki_ai.rag.lore.models import LoreHit
from smeshariki_ai.rag.lore.package import check_package

FIXTURE = Path(__file__).parents[3] / "fixtures" / "lore_benchmark"


def hit(document_id: str, text: str) -> LoreHit:
    return LoreHit(
        chunk_id=1,
        document_id=document_id,
        position=0,
        title=document_id.upper(),
        text=text,
        score=1.0,
        rank=1,
    )


class ScriptedProvider(LLMProvider):
    def __init__(self, content: str) -> None:
        self.content = content
        self.messages: tuple[Message, ...] = ()

    async def stream(
        self,
        messages: Sequence[Message],
        tools: Sequence[object],
    ) -> AsyncIterator[LLMTextDelta | LLMResponse]:
        self.messages = tuple(messages)
        yield LLMResponse(content=self.content)


def test_fixture_has_the_course_shape() -> None:
    check = check_package(FIXTURE / "lore")
    questions = read_benchmark_questions(FIXTURE / "questions.yaml")

    normal = [item for item in questions.questions if item.kind == "normal"]
    traps = [item for item in questions.questions if item.kind == "trap"]

    assert check.valid is True
    assert check.document_count == 30
    assert len(normal) == 10
    assert len(traps) == 5
    assert all(len(item.relevant_documents) >= 3 for item in normal)
    assert all(not item.relevant_documents for item in traps)


async def test_fixture_benchmark_metrics_with_prepared_answers() -> None:
    questions = read_benchmark_questions(FIXTURE / "questions.yaml")
    answers = json.loads((FIXTURE / "answers.json").read_text(encoding="utf-8"))
    runner = BenchmarkRunner(MorphAnalyzer(), StaticAnswerer(answers), k=5)

    report = await runner.run(FIXTURE / "lore", questions)

    assert report.document_count == 30
    assert report.normal_count == 10
    assert report.trap_count == 5
    assert report.recall_at_k is not None and report.recall_at_k >= 0.8
    assert report.mrr is not None and report.mrr >= 0.9
    assert report.accuracy is not None and report.accuracy >= 0.8
    assert report.correct_rejection_rate == 1.0
    assert len(report.results) == 15


async def test_wrong_answer_reduces_accuracy(tmp_path: Path) -> None:
    questions = read_benchmark_questions(FIXTURE / "questions.yaml")
    answers = json.loads((FIXTURE / "answers.json").read_text(encoding="utf-8"))
    answers["q01"] = "Неверный ответ."
    runner = BenchmarkRunner(MorphAnalyzer(), StaticAnswerer(answers), k=5)

    report = await runner.run(FIXTURE / "lore", questions)

    assert report.accuracy is not None
    assert report.accuracy < 1.0
    q01 = next(item for item in report.results if item.question_id == "q01")
    assert q01.correct is False


async def test_missing_answer_is_a_safe_error() -> None:
    questions = read_benchmark_questions(FIXTURE / "questions.yaml")
    runner = BenchmarkRunner(MorphAnalyzer(), StaticAnswerer({}), k=5)

    with pytest.raises(BenchmarkError):
        await runner.run(FIXTURE / "lore", questions)


async def test_llm_answerer_uses_the_retrieved_passages() -> None:
    provider = ScriptedProvider("Ответ по фрагменту [d01].")
    answerer = LiteLLMAnswerer(provider)
    question = BenchmarkQuestion(
        id="q01",
        text="Что в документе?",
        kind="normal",
        relevant_documents=("d01", "d02", "d03"),
        reference_answer="Ответ.",
        required_facts=("Ответ",),
    )

    answer = await answerer.answer(question, (hit("d01", "Нужный текст."),))

    assert answer == "Ответ по фрагменту [d01]."
    assert "[d01]" in provider.messages[1].content
    assert "Нужный текст." in provider.messages[1].content


def test_question_shape_is_validated(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        BenchmarkQuestion(
            id="q01",
            text="Вопрос",
            kind="normal",
            relevant_documents=("d01", "d02"),
            reference_answer="Ответ",
            required_facts=("факт",),
        )
    with pytest.raises(ValueError):
        BenchmarkQuestion(
            id="q02",
            text="Вопрос",
            kind="trap",
            relevant_documents=("d01",),
            reference_answer="Ответ",
        )
    with pytest.raises(ValueError):
        BenchmarkQuestion(
            id="q03",
            text="Вопрос",
            kind="normal",
            relevant_documents=("d01", "d02", "d03"),
            reference_answer="Ответ",
            required_facts=(),
        )


def test_invalid_questions_file_is_a_safe_error(tmp_path: Path) -> None:
    path = tmp_path / "questions.yaml"
    path.write_text("not: a benchmark\n", encoding="utf-8")

    with pytest.raises(BenchmarkError):
        read_benchmark_questions(path)

    with pytest.raises(BenchmarkError):
        read_benchmark_questions(tmp_path / "missing.yaml")
