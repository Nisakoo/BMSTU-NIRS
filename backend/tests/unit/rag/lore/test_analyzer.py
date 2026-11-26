from __future__ import annotations

import pytest

from smeshariki_ai.rag.lore.analyzer import (
    MorphAnalyzer,
    SimpleAnalyzer,
    normalize_text,
)


def test_normalize_text_folds_case_spaces_and_yo() -> None:
    assert normalize_text("  Ёжик   и КРОШ ") == "ежик и крош"


def test_simple_analyzer_keeps_words_and_hyphenated_names() -> None:
    analyzer = SimpleAnalyzer()
    assert analyzer.terms("Кар-Карыч и Пин-механик, ёлки!") == (
        "кар-карыч",
        "пин-механик",
        "елки",
    )


def test_analyzers_drop_stop_words() -> None:
    assert "и" not in SimpleAnalyzer().terms("Крош и Ёжик")
    assert "и" not in MorphAnalyzer().terms("Крош и Ёжик")
    assert MorphAnalyzer().terms("что это было") == ()


def test_morph_analyzer_lemmatizes_russian_forms() -> None:
    analyzer = MorphAnalyzer()
    assert analyzer.terms("возвращают билеты") == ("возвращать", "билет")
    assert analyzer.terms("билета") == ("билет",)


def test_morph_analyzer_keeps_names_and_hyphenated_terms() -> None:
    analyzer = MorphAnalyzer()
    assert analyzer.terms("Крош и Ёжик") == ("крош", "ежик")
    assert analyzer.terms("Кар-Карыч") == ("кар-карыч",)


def test_morph_analyzer_keeps_unknown_words() -> None:
    analyzer = MorphAnalyzer()
    assert analyzer.terms("смешарикиада") == ("смешарикиада",)


@pytest.mark.parametrize("text", ["", "   ", "!!! ..."])
def test_analyzers_return_no_terms_for_empty_text(text: str) -> None:
    assert SimpleAnalyzer().terms(text) == ()
    assert MorphAnalyzer().terms(text) == ()


def test_morph_query_and_document_share_terms() -> None:
    analyzer = MorphAnalyzer()
    document = set(analyzer.terms("В магазине продают билеты на поезд."))
    query = set(analyzer.terms("Где купить билет?"))
    assert {"билет"} <= document
    assert {"билет"} <= query
