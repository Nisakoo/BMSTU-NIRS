from __future__ import annotations

import pytest

from smeshariki_ai.rag.lore.context import (
    EMPTY_MESSAGE,
    LoreContextBuilder,
)
from smeshariki_ai.rag.lore.models import LoreHit, LoreSearchResult


def hit(
    document_id: str,
    score: float,
    text: str = "Текст фрагмента.",
    position: int = 0,
) -> LoreHit:
    return LoreHit(
        chunk_id=1,
        document_id=document_id,
        position=position,
        title=document_id.upper(),
        source="Синтетика",
        text=text,
        score=score,
        rank=1,
    )


def result(*hits: LoreHit) -> LoreSearchResult:
    return LoreSearchResult(hits=tuple(hits), total=len(hits), version=1)


def test_empty_search_returns_empty_context() -> None:
    context = LoreContextBuilder().build(result())

    assert context.status == "empty"
    assert context.passages == ()
    assert context.message == EMPTY_MESSAGE


def test_at_most_three_passages_and_one_per_document() -> None:
    context = LoreContextBuilder().build(
        result(
            hit("a", 10.0),
            hit("a", 9.0, position=1),
            hit("b", 8.0),
            hit("c", 7.0),
            hit("d", 6.0),
        )
    )

    assert context.status == "found"
    assert [passage.title for passage in context.passages] == ["A", "B", "C"]
    assert all("score" not in passage.model_dump() for passage in context.passages)
    assert all(
        "document_id" not in passage.model_dump() for passage in context.passages
    )


def test_weak_matches_are_dropped() -> None:
    context = LoreContextBuilder().build(
        result(hit("a", 10.0), hit("b", 4.9), hit("c", 4.0))
    )

    assert [passage.title for passage in context.passages] == ["A"]


def test_long_text_is_clipped_to_the_character_budget() -> None:
    context = LoreContextBuilder(max_chars=100).build(
        result(hit("a", 10.0, text="я" * 500))
    )

    assert len(context.passages) == 1
    assert len(context.passages[0].text) <= 100
    assert context.passages[0].text.endswith("…")


def test_character_budget_is_shared_by_all_passages() -> None:
    context = LoreContextBuilder(max_chars=60).build(
        result(
            hit("a", 10.0, text="первый " * 5),
            hit("b", 9.0, text="второй " * 5),
            hit("c", 8.0, text="третий " * 5),
        )
    )

    total = sum(len(passage.text) for passage in context.passages)
    assert total <= 60
    assert [passage.title for passage in context.passages] == ["A", "B"]


def test_no_passages_after_filtering_is_empty() -> None:
    context = LoreContextBuilder().build(result(hit("a", 10.0, text="   ")))

    assert context.status == "empty"
    assert context.message == EMPTY_MESSAGE


def test_invalid_builder_settings_are_rejected() -> None:
    with pytest.raises(ValueError):
        LoreContextBuilder(retrieval_k=0)
    with pytest.raises(ValueError):
        LoreContextBuilder(max_passages=0)
    with pytest.raises(ValueError):
        LoreContextBuilder(max_chars=0)
    with pytest.raises(ValueError):
        LoreContextBuilder(score_ratio=1.1)
