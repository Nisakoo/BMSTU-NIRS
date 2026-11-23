from __future__ import annotations

import pytest

from smeshariki_ai.rag.lore.chunking import (
    ChunkingConfig,
    chunk_text,
    count_words,
)


def test_short_text_becomes_one_chunk() -> None:
    assert chunk_text("Крош и Ёжик пошли гулять.") == ("Крош и Ёжик пошли гулять.",)


def test_empty_text_has_no_chunks() -> None:
    assert chunk_text("") == ()
    assert chunk_text("   \n\n  ") == ()


def test_chunks_respect_the_configured_maximum() -> None:
    sentences = [f"Предложение номер {index} " + "слово " * 18 for index in range(20)]
    text = " ".join(f"{sentence.strip()}." for sentence in sentences)
    config = ChunkingConfig(
        min_words=40, target_words=100, max_words=140, overlap_words=30
    )

    chunks = chunk_text(text, config)

    assert len(chunks) > 1
    assert all(count_words(chunk) <= config.max_words for chunk in chunks)
    assert all(chunk.strip() for chunk in chunks)


def test_chunks_overlap_between_boundaries() -> None:
    sentences = [
        "Первое предложение содержит несколько нужных слов для проверки перекрытия.",
        "Второе предложение продолжает мысль и добавляет новые подробности.",
        "Третье предложение завершает небольшой фрагмент текста.",
        "Четвёртое предложение начинает следующий смысловой блок.",
        "Пятое предложение добавляет ещё немного текста для длины.",
    ]
    config = ChunkingConfig(
        min_words=5, target_words=12, max_words=20, overlap_words=10
    )

    chunks = chunk_text(" ".join(sentences), config)

    assert len(chunks) > 1
    last_sentence = chunks[0].rsplit(". ", 1)[-1]
    assert last_sentence in chunks[1]


def test_long_sentence_is_split_by_words() -> None:
    text = " ".join(f"слово{index}" for index in range(50))
    config = ChunkingConfig(min_words=5, target_words=10, max_words=15, overlap_words=3)

    chunks = chunk_text(text, config)

    assert len(chunks) > 1
    assert all(count_words(chunk) <= config.max_words for chunk in chunks)


def test_invalid_chunking_config_is_rejected() -> None:
    with pytest.raises(ValueError):
        ChunkingConfig(min_words=0)
    with pytest.raises(ValueError):
        ChunkingConfig(min_words=100, target_words=50)
    with pytest.raises(ValueError):
        ChunkingConfig(target_words=100, overlap_words=100)
