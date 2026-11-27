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
    BenchmarkSet,
    StaticAnswerer,
    read_benchmark_questions,
)
from smeshariki_ai.rag.lore.benchmark_llm import LiteLLMAnswerer
from smeshariki_ai.rag.lore.context import LoreContext, LoreContextBuilder, LorePassage
from smeshariki_ai.rag.lore.expansion import QueryExpander
from smeshariki_ai.rag.lore.models import LoreHit
from smeshariki_ai.rag.lore.rerank import Ranker

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


async def test_llm_answerer_prefers_the_built_context() -> None:
    provider = ScriptedProvider("Ответ.")
    answerer = LiteLLMAnswerer(provider)
    question = BenchmarkQuestion(
        id="q01",
        text="Во что играют герои?",
        kind="normal",
        relevant_documents=("d01", "d02", "d03"),
        reference_answer="В футбол.",
        required_facts=("футбол",),
    )
    context = LoreContext(
        status="found",
        passages=(LorePassage(title="Футбол", source=None, text="Играют в футбол."),),
    )

    await answerer.answer(question, (hit("d01", "Сырой чанк."),), context)

    prompt = provider.messages[1].content
    assert "[Футбол] Играют в футбол." in prompt
    assert "Сырой чанк." not in prompt


async def test_llm_answerer_falls_back_when_the_context_is_empty() -> None:
    provider = ScriptedProvider("Ответ.")
    answerer = LiteLLMAnswerer(provider)
    question = BenchmarkQuestion(
        id="q01",
        text="Что в документе?",
        kind="normal",
        relevant_documents=("d01", "d02", "d03"),
        reference_answer="Ответ.",
        required_facts=("Ответ",),
    )

    await answerer.answer(
        question,
        (hit("d01", "Сырой чанк."),),
        LoreContext(status="empty"),
    )

    assert "[d01]" in provider.messages[1].content


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


MINI_QUESTIONS = """\
questions:
- id: q01
  text: Какие блюда из морковки готовят герои?
  kind: normal
  relevant_documents: [d01, d02, d03]
  reference_answer: Блюдо из морковки.
  required_facts: [блюдо]
- id: t01
  text: Крош и Ёжик
  kind: trap
  reference_answer: В документах нет этой информации.
- id: t02
  text: Какая машина у Пина?
  kind: trap
  reference_answer: В документах нет этой информации.
"""

MINI_ANSWERS = {
    "q01": "Блюдо из морковки.",
    "t01": "В документах нет этой информации.",
    "t02": "В документах нет этой информации.",
}


def write_mini_package(root: Path) -> None:
    documents = {
        "d01": (
            "Блюда из морковки",
            "Блюдо из морковки — любимое блюдо. Морковка полезна. "
            "Блюдо из морковки просто готовить.",
        ),
        "d02": (
            "Разговор Кроша",
            "Крош вспоминает морковку. Морковка — любимый овощ Кроша.",
        ),
        "d03": (
            "Машина Пина",
            "Машина Пина едет быстро. Машина — полезная штука.",
        ),
    }
    root.mkdir(parents=True, exist_ok=True)
    (root / "package.yaml").write_text("format_version: 1\n", encoding="utf-8")
    documents_dir = root / "documents"
    documents_dir.mkdir()
    for document_id, (title, text) in documents.items():
        (documents_dir / f"{document_id}.yaml").write_text(
            f"id: {document_id}\ntitle: {title}\ntext: |\n  {text}\n",
            encoding="utf-8",
        )


def mini_questions(root: Path) -> BenchmarkSet:
    path = root / "questions.yaml"
    path.write_text(MINI_QUESTIONS, encoding="utf-8")
    return read_benchmark_questions(path)


async def test_context_metrics_measure_the_agent_path(tmp_path: Path) -> None:
    package = tmp_path / "lore"
    write_mini_package(package)
    questions = mini_questions(tmp_path)
    runner = BenchmarkRunner(
        MorphAnalyzer(),
        StaticAnswerer(MINI_ANSWERS),
        k=5,
        context=LoreContextBuilder(min_score=0.0),
    )

    report = await runner.run(package, questions)

    q01 = next(item for item in report.results if item.question_id == "q01")
    t01 = next(item for item in report.results if item.question_id == "t01")
    t02 = next(item for item in report.results if item.question_id == "t02")

    assert q01.context_status == "found"
    assert q01.context_documents == ("d01", "d02")
    assert q01.context_relevant == 2
    assert report.context_recall == pytest.approx(2 / 3)
    assert report.context_any_relevant == 1.0
    assert report.context_found_rate == 1.0
    assert t01.context_status == "empty"
    assert t01.context_relevant is None
    assert t02.context_status == "found"
    assert report.trap_passage_rate == 0.5
    assert report.recall_at_k == pytest.approx(2 / 3)
    assert report.mrr == 1.0


async def test_without_a_context_builder_context_metrics_are_none(
    tmp_path: Path,
) -> None:
    package = tmp_path / "lore"
    write_mini_package(package)
    questions = mini_questions(tmp_path)
    runner = BenchmarkRunner(MorphAnalyzer(), StaticAnswerer(MINI_ANSWERS), k=5)

    report = await runner.run(package, questions)

    assert report.context_recall is None
    assert report.context_any_relevant is None
    assert report.context_found_rate is None
    assert report.trap_passage_rate is None
    q01 = next(item for item in report.results if item.question_id == "q01")
    assert q01.context_status is None
    assert q01.context_documents == ()
    assert q01.context_relevant is None


async def test_context_selection_uses_only_the_first_retrieval_k_hits(
    tmp_path: Path,
) -> None:
    package = tmp_path / "lore"
    write_mini_package(package)
    questions = mini_questions(tmp_path)
    runner = BenchmarkRunner(
        MorphAnalyzer(),
        StaticAnswerer(MINI_ANSWERS),
        k=5,
        context=LoreContextBuilder(retrieval_k=1, min_score=0.0),
    )

    report = await runner.run(package, questions)

    q01 = next(item for item in report.results if item.question_id == "q01")
    assert q01.context_documents == ("d01",)
    assert q01.context_relevant == 1
    assert report.context_recall == pytest.approx(1 / 3)


class FixedExpander(QueryExpander):
    def __init__(self, terms: tuple[str, ...]) -> None:
        self.terms = terms
        self.queries: list[str] = []

    async def expand(self, query: str) -> tuple[str, ...]:
        self.queries.append(query)
        return self.terms


EXPANSION_QUESTIONS = """\
questions:
- id: q01
  text: Что герои готовят на обед?
  kind: normal
  relevant_documents: [d01, d02, d03]
  reference_answer: Блюдо из морковки.
  required_facts: [блюдо]
- id: t01
  text: Крош и Ёжик
  kind: trap
  reference_answer: В документах нет этой информации.
"""


def write_expansion_package(root: Path) -> None:
    documents = {
        "d01": ("Первое", "Морковка полезна. Морковка растёт на грядке."),
        "d02": ("Второе", "Морковка сладкая. Морковка нравится всем."),
        "d03": ("Третье", "Морковка хрустит. Морковка лежит в подвале."),
    }
    root.mkdir(parents=True, exist_ok=True)
    (root / "package.yaml").write_text("format_version: 1\n", encoding="utf-8")
    documents_dir = root / "documents"
    documents_dir.mkdir()
    for document_id, (title, text) in documents.items():
        (documents_dir / f"{document_id}.yaml").write_text(
            f"id: {document_id}\ntitle: {title}\ntext: |\n  {text}\n",
            encoding="utf-8",
        )


async def test_expander_is_used_and_can_raise_recall(tmp_path: Path) -> None:
    package = tmp_path / "lore"
    write_expansion_package(package)
    (tmp_path / "questions.yaml").write_text(EXPANSION_QUESTIONS, encoding="utf-8")
    questions = read_benchmark_questions(tmp_path / "questions.yaml")
    answers = {"q01": "Блюдо из морковки.", "t01": "В документах нет информации."}

    baseline = await BenchmarkRunner(MorphAnalyzer(), StaticAnswerer(answers), k=5).run(
        package, questions
    )

    expander = FixedExpander(("морковка",))
    expanded = await BenchmarkRunner(
        MorphAnalyzer(), StaticAnswerer(answers), k=5, expander=expander
    ).run(package, questions)

    assert expander.queries == sorted(expander.queries, key=expander.queries.index)
    assert "Что герои готовят на обед?" in expander.queries
    assert baseline.recall_at_k == 0.0
    assert expanded.recall_at_k == 1.0


async def test_document_metrics_deduplicate_before_the_slice(tmp_path: Path) -> None:
    package = tmp_path / "lore"
    write_expansion_package(package)
    (tmp_path / "questions.yaml").write_text(EXPANSION_QUESTIONS, encoding="utf-8")
    questions = read_benchmark_questions(tmp_path / "questions.yaml")
    answers = {"q01": "Блюдо из морковки.", "t01": "В документах нет информации."}
    expander = FixedExpander(("морковка",))

    report = await BenchmarkRunner(
        MorphAnalyzer(), StaticAnswerer(answers), k=1, expander=expander
    ).run(package, questions)

    assert report.document_recall_at_k is not None
    assert report.document_mrr is not None
    # With k=1 the chunk metric can only see one chunk, while the document
    # metric sees the first distinct document.
    assert report.document_recall_at_k >= report.recall_at_k
    assert report.document_mrr >= report.mrr


async def test_ranker_is_applied_before_the_context(tmp_path: Path) -> None:
    package = tmp_path / "lore"
    write_mini_package(package)
    questions = mini_questions(tmp_path)

    class ReversingRanker(Ranker):
        def __init__(self) -> None:
            self.calls = 0

        async def rerank(self, query, hits, *, limit):
            self.calls += 1
            return tuple(reversed(tuple(hits)[:limit]))

    ranker = ReversingRanker()
    report = await BenchmarkRunner(
        MorphAnalyzer(),
        StaticAnswerer(MINI_ANSWERS),
        k=5,
        context=LoreContextBuilder(min_score=0.0),
        ranker=ranker,
    ).run(package, questions)

    assert ranker.calls >= 1
    q01 = next(item for item in report.results if item.question_id == "q01")
    assert q01.context_documents


async def test_expander_returning_nothing_keeps_the_metrics(
    tmp_path: Path,
) -> None:
    package = tmp_path / "lore"
    write_expansion_package(package)
    (tmp_path / "questions.yaml").write_text(EXPANSION_QUESTIONS, encoding="utf-8")
    questions = read_benchmark_questions(tmp_path / "questions.yaml")
    answers = {"q01": "Блюдо из морковки.", "t01": "В документах нет информации."}

    baseline = await BenchmarkRunner(MorphAnalyzer(), StaticAnswerer(answers), k=5).run(
        package, questions
    )
    empty = await BenchmarkRunner(
        MorphAnalyzer(),
        StaticAnswerer(answers),
        k=5,
        expander=FixedExpander(()),
    ).run(package, questions)

    assert baseline.recall_at_k == empty.recall_at_k
    assert baseline.mrr == empty.mrr
