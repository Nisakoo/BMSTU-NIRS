from __future__ import annotations

from smeshariki_ai.rag.lore.analyzer import MorphAnalyzer, SimpleAnalyzer
from smeshariki_ai.rag.lore.stopwords import (
    FUNCTION_WORDS,
    LIGHT_VERBS,
    STOP_WORDS,
    drop_stop_words,
    stop_word_share,
)


def test_stop_words_are_normalized_lemmas() -> None:
    assert {"и", "что", "быть", "делать"} <= STOP_WORDS
    assert all(term == term.strip().casefold() for term in STOP_WORDS)
    assert not any("-" in term for term in STOP_WORDS)


def test_content_words_and_names_are_not_stop_words() -> None:
    for term in (
        "игра",
        "играть",
        "футбол",
        "гольф",
        "мороз",
        "зуб",
        "друг",
        "новый",
        "нужный",
        "крош",
        "ежик",
        "бараш",
        "пин",
    ):
        assert term not in STOP_WORDS


def test_lists_compose_the_single_source() -> None:
    assert STOP_WORDS == FUNCTION_WORDS | LIGHT_VERBS
    assert not FUNCTION_WORDS & LIGHT_VERBS


def test_drop_stop_words_keeps_order_and_duplicates() -> None:
    terms = ("крош", "и", "мороз", "и", "мороз", "быть")

    assert drop_stop_words(terms) == ("крош", "мороз", "мороз")


def test_drop_stop_words_ignores_empty_terms() -> None:
    assert drop_stop_words(("", "крош", "")) == ("крош",)


def test_stop_word_share_is_a_plain_ratio() -> None:
    assert stop_word_share(()) == 0.0
    assert stop_word_share(("и", "что", "крош", "мороз")) == 0.5


def test_morph_analyzer_drops_stop_words_from_documents_and_queries() -> None:
    analyzer = MorphAnalyzer()

    assert analyzer.terms("Что делают герои в огороде?") == ("герой", "огород")
    assert analyzer.terms("Крош и Ёжик") == ("крош", "ежик")


def test_simple_analyzer_drops_stop_words_too() -> None:
    assert SimpleAnalyzer().terms("Крош и Ёжик") == ("крош", "ежик")


def test_text_of_only_stop_words_gives_no_terms() -> None:
    assert MorphAnalyzer().terms("и что это было") == ()
    assert SimpleAnalyzer().terms("и что это было") == ()
