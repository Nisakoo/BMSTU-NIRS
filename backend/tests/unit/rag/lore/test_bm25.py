from __future__ import annotations

import pytest

from smeshariki_ai.rag.lore.bm25 import (
    Bm25Params,
    idf,
    rank,
    score,
    term_score,
    unique_terms,
)

PARAMS = Bm25Params()


def test_idf_matches_the_course_example() -> None:
    assert idf(3, 2) == pytest.approx(0.47000362924573563)


def test_idf_is_zero_for_an_absent_term_or_empty_corpus() -> None:
    assert idf(0, 0) == 0.0
    assert idf(3, 0) == 0.0


def test_term_score_saturates_repetitions() -> None:
    assert term_score(1, 4, 4.0, PARAMS) == pytest.approx(1.0)
    assert term_score(2, 4, 4.0, PARAMS) == pytest.approx(1.375)
    assert term_score(2, 4, 4.0, PARAMS) > term_score(1, 4, 4.0, PARAMS)
    assert term_score(2, 4, 4.0, PARAMS) < 2 * term_score(1, 4, 4.0, PARAMS)


def test_term_score_penalizes_a_longer_document() -> None:
    short = term_score(1, 4, 4.0, PARAMS)
    long = term_score(1, 8, 4.0, PARAMS)
    assert long < short


def test_term_score_is_safe_for_empty_values() -> None:
    assert term_score(0, 4, 4.0, PARAMS) == 0.0
    assert term_score(1, 0, 4.0, PARAMS) == 0.0
    assert term_score(1, 4, 0.0, PARAMS) == 0.0


def test_query_terms_are_deduplicated() -> None:
    assert unique_terms(["возврат", "оплаты", "возврат", ""]) == (
        "возврат",
        "оплаты",
    )


def test_score_and_rank_follow_the_course_example() -> None:
    postings = {
        "возврат": {1: 1, 3: 1},
        "оплаты": {1: 1, 2: 1},
    }
    lengths = {1: 4, 2: 4, 3: 4}
    order = {1: ("a", 0), 2: ("b", 0), 3: ("c", 0)}

    scores = score(["возврат", "оплаты"], postings, lengths, 3, 4.0, PARAMS)

    assert scores[1] == pytest.approx(0.9400072584914713)
    assert scores[2] == pytest.approx(0.47000362924573563)
    assert scores[3] == pytest.approx(0.47000362924573563)
    assert rank(scores, order, 2) == (1, 2)
    assert rank(scores, order, 10) == (1, 2, 3)


def test_score_ignores_terms_without_postings() -> None:
    scores = score(
        ["нет", "совпадений"],
        {},
        {},
        10,
        5.0,
        PARAMS,
    )
    assert scores == {}


def test_score_is_empty_for_an_empty_corpus() -> None:
    assert score(["слово"], {"слово": {1: 1}}, {1: 1}, 0, 0.0, PARAMS) == {}


def test_rank_filters_zero_scores_and_respects_top_k() -> None:
    assert rank(
        {1: 0.0, 2: 1.0, 3: 1.0}, {1: ("a", 0), 2: ("b", 0), 3: ("c", 0)}, 5
    ) == (
        2,
        3,
    )
    assert rank({1: 1.0}, {1: ("a", 0)}, 0) == ()


def test_invalid_parameters_are_rejected() -> None:
    with pytest.raises(ValueError):
        Bm25Params(k1=0)
    with pytest.raises(ValueError):
        Bm25Params(b=-0.1)
    with pytest.raises(ValueError):
        Bm25Params(b=1.1)
