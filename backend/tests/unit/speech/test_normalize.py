import pytest

from smeshariki_ai.speech.normalize import (
    SpeechChunk,
    normalize_text,
    split_for_speech,
)


def test_normalize_collapses_whitespace_and_preserves_paragraphs() -> None:
    assert normalize_text("  Крош   и\tЁжик \n\n\n\n строят  ракету  ") == (
        "Крош и Ёжик\n\nстроят ракету"
    )


def test_normalize_removes_common_markdown_but_keeps_dialogue_dashes() -> None:
    text = "# Название\n\n**Крош** и __Ёжик__\n\n— Привет! — сказал Крош."

    assert normalize_text(text) == (
        "Название\n\nКрош и Ёжик\n\n— Привет! — сказал Крош."
    )


def test_normalize_turns_markdown_links_into_their_text() -> None:
    assert normalize_text("Смотри [луну](https://example.test) и <b>звёзды</b>.") == (
        "Смотри луну и звёзды."
    )


def test_normalize_puts_no_space_before_punctuation() -> None:
    assert normalize_text("Привет , Крош !") == "Привет, Крош!"


def test_split_returns_empty_tuple_for_blank_text() -> None:
    assert split_for_speech(" \n\t ", max_chars=100) == ()


def test_split_packs_sentences_and_adds_a_paragraph_pause() -> None:
    chunks = split_for_speech(
        "Первое предложение. Второе предложение.\n\nНовый абзац.",
        max_chars=200,
    )

    assert chunks == (
        SpeechChunk("Первое предложение. Второе предложение.", 350),
        SpeechChunk("Новый абзац.", 350),
    )


def test_split_respects_the_character_limit_and_keeps_every_word() -> None:
    text = "Крош бежит. Ёжик идёт. Нюша поёт. Бараш пишет."

    chunks = split_for_speech(text, max_chars=25)

    assert all(len(chunk.text) <= 25 for chunk in chunks)
    assert " ".join(chunk.text for chunk in chunks) == text


def test_split_breaks_a_single_very_long_word() -> None:
    chunks = split_for_speech("а" * 25, max_chars=10)

    assert [chunk.text for chunk in chunks] == ["а" * 10, "а" * 10, "а" * 5]


@pytest.mark.parametrize("max_chars", [0, -1])
def test_split_rejects_a_non_positive_limit(max_chars: int) -> None:
    with pytest.raises(ValueError):
        split_for_speech("Текст", max_chars=max_chars)
