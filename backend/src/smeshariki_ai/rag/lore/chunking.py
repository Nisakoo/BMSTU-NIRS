"""Deterministic chunking of narrative documents for BM25."""

from __future__ import annotations

import re
from dataclasses import dataclass

_SENTENCE_BREAK = re.compile(r"(?<=[.!?…])\s+")
_PARAGRAPH_BREAK = re.compile(r"\n\s*\n")
_WORD = re.compile(r"\S+")


@dataclass(frozen=True, slots=True)
class ChunkingConfig:
    min_words: int = 60
    target_words: int = 220
    max_words: int = 320
    overlap_words: int = 40

    def __post_init__(self) -> None:
        if self.min_words <= 0:
            raise ValueError("min_words must be positive")
        if not self.min_words <= self.target_words <= self.max_words:
            raise ValueError("expected min_words <= target_words <= max_words")
        if self.overlap_words < 0:
            raise ValueError("overlap_words must not be negative")
        if self.overlap_words >= self.target_words:
            raise ValueError("overlap_words must be smaller than target_words")


def count_words(text: str) -> int:
    return len(_WORD.findall(text))


def chunk_text(text: str, config: ChunkingConfig | None = None) -> tuple[str, ...]:
    """Split a document into overlapping, sentence-aligned chunks.

    Paragraph breaks are kept as sentence separators. A sentence longer than
    ``max_words`` is split into word windows; normal prose stays intact.
    """

    settings = config or ChunkingConfig()
    sentences = _sentences(text, settings.max_words)
    if not sentences:
        return ()

    chunks: list[str] = []
    current: list[str] = []

    def words(items: list[str]) -> int:
        return sum(count_words(item) for item in items)

    def flush() -> None:
        nonlocal current
        if current:
            chunks.append(" ".join(current).strip())
            current = []

    def overlap() -> list[str]:
        if not current or settings.overlap_words <= 0:
            return []
        tail: list[str] = []
        total = 0
        for sentence in reversed(current):
            size = count_words(sentence)
            if tail and total + size > settings.overlap_words:
                break
            if not tail and size > settings.overlap_words:
                break
            tail.append(sentence)
            total += size
        return list(reversed(tail))

    for index, sentence in enumerate(sentences):
        has_next = index + 1 < len(sentences)
        sentence_words = count_words(sentence)

        if current and words(current) + sentence_words > settings.max_words:
            previous = overlap() if has_next else []
            flush()
            current = previous

        if current and words(current) + sentence_words > settings.max_words:
            # The overlap itself leaves no room for the sentence; start clean.
            flush()

        current.append(sentence)
        if words(current) >= settings.target_words:
            previous = overlap() if has_next else []
            flush()
            current = previous

    flush()
    return tuple(_merge_short_tail(chunks, settings))


def _sentences(text: str, max_words: int) -> list[str]:
    sentences: list[str] = []
    for paragraph in _PARAGRAPH_BREAK.split(text.strip()):
        paragraph = " ".join(paragraph.split())
        if not paragraph:
            continue
        for sentence in _SENTENCE_BREAK.split(paragraph):
            sentence = sentence.strip()
            if not sentence:
                continue
            sentences.extend(_split_long_sentence(sentence, max_words))
    return sentences


def _split_long_sentence(sentence: str, max_words: int) -> list[str]:
    words = _WORD.findall(sentence)
    if len(words) <= max_words:
        return [sentence]
    return [
        " ".join(words[start : start + max_words])
        for start in range(0, len(words), max_words)
    ]


def _merge_short_tail(chunks: list[str], config: ChunkingConfig) -> list[str]:
    if len(chunks) < 2 or count_words(chunks[-1]) >= config.min_words:
        return chunks
    if count_words(chunks[-2]) + count_words(chunks[-1]) <= config.max_words:
        chunks[-2] = f"{chunks[-2]} {chunks[-1]}"
        chunks.pop()
    return chunks
