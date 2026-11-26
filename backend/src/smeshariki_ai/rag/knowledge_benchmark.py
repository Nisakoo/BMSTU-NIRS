"""Offline quality benchmark of the exact knowledge lookup.

The lore benchmark measures narrative search; this one measures the structured
canon: does ``lookup_knowledge`` find a character, place, item or episode by its
exact name, alias, episode title or a typo, and does it reject a name that is
not in the canon.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from smeshariki_ai.rag.lookup import KnowledgeLookup, LookupResult
from smeshariki_ai.rag.memory import InMemoryKnowledgeStore
from smeshariki_ai.rag.models import Slug
from smeshariki_ai.rag.services import load_package
from smeshariki_ai.rag.yaml_reader import YamlReadError, read_yaml_file

QuestionKind = Literal["exact", "alias", "episode", "typo", "negative"]


class KnowledgeBenchmarkError(Exception):
    """A safe benchmark error without corpus or answer text."""


class KnowledgeBenchmarkQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: Slug
    query: str = Field(min_length=1, max_length=200)
    kind: QuestionKind
    expected: str | None = Field(default=None, max_length=100)

    @property
    def needs_expected(self) -> bool:
        return self.kind != "negative"


class KnowledgeBenchmarkSet(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    questions: tuple[KnowledgeBenchmarkQuestion, ...] = Field(min_length=1)


class KnowledgeQuestionResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    question_id: str
    query: str
    kind: str
    expected: str | None = None
    status: str
    matched: tuple[str, ...] = ()
    suggested: tuple[str, ...] = ()
    correct: bool


class KnowledgeBenchmarkReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    question_count: int = Field(ge=0)
    exact_count: int = Field(ge=0)
    typo_count: int = Field(ge=0)
    negative_count: int = Field(ge=0)
    accuracy: float | None = None
    exact_match_rate: float | None = None
    suggestion_rate: float | None = None
    false_positive_rate: float | None = None
    results: tuple[KnowledgeQuestionResult, ...] = ()


class KnowledgeBenchmarkRunner:
    def __init__(self, lookup: KnowledgeLookup) -> None:
        self._lookup = lookup

    async def run(
        self,
        package: Path,
        questions: KnowledgeBenchmarkSet,
    ) -> KnowledgeBenchmarkReport:
        store = InMemoryKnowledgeStore()
        loaded = await load_package(package, store)
        if not loaded.loaded:
            raise KnowledgeBenchmarkError("the knowledge package could not be loaded")
        lookup = KnowledgeLookup(store)

        results: list[KnowledgeQuestionResult] = []
        for question in questions.questions:
            result = await lookup.lookup(question.query)
            results.append(_evaluate(question, result))

        direct = [
            item for item in results if item.kind in ("exact", "alias", "episode")
        ]
        typos = [item for item in results if item.kind == "typo"]
        negatives = [item for item in results if item.kind == "negative"]
        return KnowledgeBenchmarkReport(
            question_count=len(results),
            exact_count=len(direct),
            typo_count=len(typos),
            negative_count=len(negatives),
            accuracy=_mean(item.correct for item in results),
            exact_match_rate=_mean(item.correct for item in direct),
            suggestion_rate=_mean(item.correct for item in typos),
            false_positive_rate=(
                None
                if not negatives
                else sum(1 for item in negatives if not item.correct) / len(negatives)
            ),
            results=tuple(results),
        )


def _evaluate(
    question: KnowledgeBenchmarkQuestion,
    result: LookupResult,
) -> KnowledgeQuestionResult:
    matched = tuple(card.id for card in result.matches)
    suggested = tuple(suggestion.id for suggestion in result.suggestions)
    if question.kind == "negative":
        correct = result.status != "found"
    elif question.kind == "typo":
        # The typo may still land exactly, or the model gets a suggestion.
        correct = question.expected in matched or question.expected in suggested
    else:
        correct = question.expected in matched
    return KnowledgeQuestionResult(
        question_id=question.id,
        query=question.query,
        kind=question.kind,
        expected=question.expected,
        status=result.status,
        matched=matched,
        suggested=suggested,
        correct=correct,
    )


def read_knowledge_questions(path: Path) -> KnowledgeBenchmarkSet:
    try:
        data = read_yaml_file(path)
    except YamlReadError as error:
        raise KnowledgeBenchmarkError(
            f"questions file is invalid: {error.code}"
        ) from error
    except OSError as error:
        raise KnowledgeBenchmarkError("questions file cannot be read") from error
    try:
        return KnowledgeBenchmarkSet.model_validate(data)
    except ValueError as error:
        raise KnowledgeBenchmarkError(
            "questions file does not match its schema"
        ) from error


def _mean(values: Sequence[bool]) -> float | None:
    present = list(values)
    if not present:
        return None
    return sum(1 for value in present if value) / len(present)


__all__ = [
    "KnowledgeBenchmarkError",
    "KnowledgeBenchmarkQuestion",
    "KnowledgeBenchmarkReport",
    "KnowledgeBenchmarkRunner",
    "KnowledgeBenchmarkSet",
    "QuestionKind",
    "read_knowledge_questions",
]
