"""Offline BM25 benchmark: corpus, questions, metrics and answer checks."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Literal, Protocol

from pydantic import Field, model_validator

from smeshariki_ai.rag.lore.analyzer import TextAnalyzer, normalize_text
from smeshariki_ai.rag.lore.index import InMemoryBm25Index
from smeshariki_ai.rag.lore.models import (
    LoreHit,
    LoreModel,
    LoreQuery,
    NonEmptyText,
    Slug,
)
from smeshariki_ai.rag.lore.services import LoadLore, SearchLore
from smeshariki_ai.rag.yaml_reader import YamlReadError, read_yaml_file

REFUSAL_MARKERS = (
    "нет этой информации",
    "нет информации",
    "нет сведений",
    "не найдено",
    "не содержится",
    "не могу ответить",
    "в документах нет",
)


class BenchmarkError(Exception):
    """A safe benchmark error without corpus or answer text."""


class BenchmarkQuestion(LoreModel):
    id: Slug
    text: NonEmptyText
    kind: Literal["normal", "trap"]
    relevant_documents: tuple[Slug, ...] = ()
    reference_answer: NonEmptyText
    required_facts: tuple[NonEmptyText, ...] = ()

    @model_validator(mode="after")
    def _question_shape(self) -> BenchmarkQuestion:
        if self.kind == "normal":
            if len(self.relevant_documents) < 3:
                raise ValueError(
                    "normal questions need at least three relevant documents"
                )
            if not self.required_facts:
                raise ValueError("normal questions need required facts")
        else:
            if self.relevant_documents:
                raise ValueError("trap questions must not have relevant documents")
            if self.required_facts:
                raise ValueError("trap questions must not have required facts")
        return self


class BenchmarkSet(LoreModel):
    questions: tuple[BenchmarkQuestion, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _unique_ids(self) -> BenchmarkSet:
        ids = [question.id for question in self.questions]
        if len(ids) != len(set(ids)):
            raise ValueError("question ids must be unique")
        return self


class Answerer(Protocol):
    async def answer(
        self,
        question: BenchmarkQuestion,
        hits: Sequence[LoreHit],
    ) -> str: ...


class BenchmarkQuestionResult(LoreModel):
    question_id: str
    text: str
    kind: str
    relevant_documents: tuple[str, ...] = ()
    retrieved_documents: tuple[str, ...] = ()
    recall: float | None = None
    reciprocal_rank: float | None = None
    answer: str = ""
    correct: bool | None = None


class BenchmarkReport(LoreModel):
    k: int = Field(ge=1)
    document_count: int = Field(ge=0)
    question_count: int = Field(ge=0)
    normal_count: int = Field(ge=0)
    trap_count: int = Field(ge=0)
    recall_at_k: float | None = None
    mrr: float | None = None
    accuracy: float | None = None
    correct_rejection_rate: float | None = None
    results: tuple[BenchmarkQuestionResult, ...] = ()


class StaticAnswerer:
    """Answers from a prepared JSON mapping, for tests and offline evaluation."""

    def __init__(self, answers: Mapping[str, str]) -> None:
        self._answers = dict(answers)

    async def answer(
        self,
        question: BenchmarkQuestion,
        hits: Sequence[LoreHit],
    ) -> str:
        try:
            return self._answers[question.id]
        except KeyError as error:
            raise BenchmarkError(
                f"no answer supplied for question {question.id}"
            ) from error


class BenchmarkRunner:
    def __init__(
        self,
        analyzer: TextAnalyzer,
        answerer: Answerer,
        *,
        k: int = 5,
    ) -> None:
        if k <= 0:
            raise ValueError("k must be positive")
        self._analyzer = analyzer
        self._answerer = answerer
        self._k = k

    async def run(
        self,
        package_path: Path,
        questions: BenchmarkSet,
    ) -> BenchmarkReport:
        index = InMemoryBm25Index()
        loaded = await LoadLore(self._analyzer).load(package_path, index)
        if not loaded.loaded or loaded.summary is None:
            raise BenchmarkError("the lore package could not be loaded")

        search = SearchLore(index, self._analyzer)
        results: list[BenchmarkQuestionResult] = []
        for question in questions.questions:
            result = await search.search(LoreQuery(text=question.text, top_k=self._k))
            retrieved = tuple(dict.fromkeys(hit.document_id for hit in result.hits))
            relevant = set(question.relevant_documents)
            found = relevant & set(retrieved)
            recall = len(found) / len(relevant) if relevant else None
            reciprocal_rank = _reciprocal_rank(retrieved, relevant)
            answer = await self._answerer.answer(question, result.hits)
            correct = _is_correct(question, answer)
            results.append(
                BenchmarkQuestionResult(
                    question_id=question.id,
                    text=question.text,
                    kind=question.kind,
                    relevant_documents=question.relevant_documents,
                    retrieved_documents=retrieved,
                    recall=recall,
                    reciprocal_rank=reciprocal_rank,
                    answer=answer,
                    correct=correct,
                )
            )

        normal = [item for item in results if item.kind == "normal"]
        traps = [item for item in results if item.kind == "trap"]
        return BenchmarkReport(
            k=self._k,
            document_count=loaded.summary.document_count,
            question_count=len(results),
            normal_count=len(normal),
            trap_count=len(traps),
            recall_at_k=_mean(item.recall for item in normal),
            mrr=_mean(item.reciprocal_rank for item in normal),
            accuracy=_mean(item.correct for item in normal),
            correct_rejection_rate=_mean(item.correct for item in traps),
            results=tuple(results),
        )


def read_benchmark_questions(path: Path) -> BenchmarkSet:
    try:
        data = read_yaml_file(path)
    except YamlReadError as error:
        raise BenchmarkError(f"questions file is invalid: {error.code}") from error
    except OSError as error:
        raise BenchmarkError("questions file cannot be read") from error
    try:
        return BenchmarkSet.model_validate(data)
    except ValueError as error:
        raise BenchmarkError("questions file does not match its schema") from error


def _reciprocal_rank(retrieved: Sequence[str], relevant: set[str]) -> float | None:
    if not relevant:
        return None
    for rank, document_id in enumerate(retrieved, start=1):
        if document_id in relevant:
            return 1.0 / rank
    return 0.0


def _is_correct(question: BenchmarkQuestion, answer: str) -> bool:
    normalized = normalize_text(answer)
    if question.kind == "trap":
        return any(marker in normalized for marker in REFUSAL_MARKERS)
    facts = [normalize_text(fact) for fact in question.required_facts]
    return bool(facts) and all(fact in normalized for fact in facts)


def _mean(values: Sequence[float | None]) -> float | None:
    present = [value for value in values if value is not None]
    if not present:
        return None
    return sum(present) / len(present)
