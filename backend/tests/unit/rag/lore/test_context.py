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
    context = LoreContextBuilder(max_passages=3).build(
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


def test_weak_matches_are_dropped_by_an_absolute_floor() -> None:
    context = LoreContextBuilder(min_score=5.0).build(
        result(hit("a", 10.0), hit("b", 4.9), hit("c", 4.0))
    )

    assert [passage.title for passage in context.passages] == ["A"]


def test_absolute_floor_keeps_a_second_relevant_episode() -> None:
    # The first story is much stronger but the second is still relevant: a
    # relative cutoff would drop it, an absolute floor keeps it.
    context = LoreContextBuilder(min_score=2.0).build(
        result(hit("a", 7.3), hit("b", 3.6), hit("c", 3.4))
    )

    assert [passage.title for passage in context.passages] == ["A", "B", "C"]


def test_name_only_query_returns_empty_context() -> None:
    context = LoreContextBuilder().build(
        result(hit("a", 10.0)),
        query_terms=("крош", "и", "ежик"),
    )

    assert context.status == "empty"
    assert context.passages == ()


def test_query_with_a_content_term_is_not_rejected() -> None:
    context = LoreContextBuilder().build(
        result(hit("a", 10.0)),
        query_terms=("крош", "строить", "скамейка"),
    )

    assert context.status == "found"


def test_builder_without_query_terms_does_not_apply_the_content_rule() -> None:
    context = LoreContextBuilder().build(result(hit("a", 10.0)))

    assert context.status == "found"


def test_long_text_is_clipped_to_the_character_budget() -> None:
    context = LoreContextBuilder(max_chars=100).build(
        result(hit("a", 10.0, text="я" * 500))
    )

    assert len(context.passages) == 1
    assert len(context.passages[0].text) <= 100
    assert context.passages[0].text.endswith("…")


def test_clipping_prefers_a_sentence_end() -> None:
    sentence = "Крош и Ёжик играют на полянке и смеются. " * 8
    limit = 200
    context = LoreContextBuilder(max_chars=limit).build(
        result(hit("a", 10.0, text=f"{sentence}{'х' * 400}"))
    )

    text = context.passages[0].text
    assert len(text) <= limit
    assert text.endswith(".")
    assert not text.endswith("…")


def test_a_stub_below_the_minimum_is_not_shown() -> None:
    context = LoreContextBuilder(max_chars=120).build(
        result(
            hit("a", 10.0, text="первый " * 30),
            hit("b", 9.0, text="второй " * 30),
        )
    )

    assert [passage.title for passage in context.passages] == ["A"]
    assert len(context.passages[0].text) <= 120


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
        LoreContextBuilder(min_score=-1)


def test_select_returns_the_same_passages_build_uses() -> None:
    builder = LoreContextBuilder()
    search_result = result(
        hit("a", 10.0, text="Первый фрагмент."),
        hit("a", 9.0, position=1, text="Дубль первого документа."),
        hit("b", 8.0, text="Второй фрагмент."),
        hit("c", 7.0, text="Третий фрагмент."),
    )

    selected = builder.select(search_result)
    context = builder.build(search_result)

    assert [item[0].document_id for item in selected] == ["a", "b", "c"]
    assert [item[1] for item in selected] == [
        passage.text for passage in context.passages
    ]
    assert context.status == "found"


def test_select_keeps_internal_ids_and_scores_that_build_drops() -> None:
    selected = LoreContextBuilder().select(result(hit("d01", 10.0)))

    assert selected[0][0].document_id == "d01"
    assert selected[0][0].score == 10.0
    assert selected[0][1] == "Текст фрагмента."


def test_select_returns_empty_for_a_name_only_query() -> None:
    selected = LoreContextBuilder().select(
        result(hit("a", 10.0)),
        query_terms=("крош", "и", "ежик"),
    )

    assert selected == ()


def test_select_returns_empty_when_no_hits_were_found() -> None:
    assert LoreContextBuilder().select(result()) == ()


def test_select_applies_the_absolute_floor() -> None:
    builder = LoreContextBuilder(min_score=5.0)
    selected = builder.select(
        result(
            hit("a", 10.0, text="а" * 30),
            hit("b", 4.9, text="б" * 30),
        )
    )

    assert [item[0].document_id for item in selected] == ["a"]
    assert selected[0][1] == "а" * 30


def test_select_clips_text_to_the_shared_character_budget() -> None:
    builder = LoreContextBuilder(max_chars=45)
    selected = builder.select(
        result(
            hit("a", 10.0, text="а" * 40),
            hit("b", 9.0, text="б" * 30),
        )
    )

    assert [item[0].document_id for item in selected] == ["a", "b"]
    assert selected[0][1] == "а" * 40
    assert selected[1][1] == "б" * 4 + "…"
