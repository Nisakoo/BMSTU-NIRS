import re
from dataclasses import dataclass

NORMALIZATION_VERSION = "1"

_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?…])\s+")
_PARAGRAPH_BOUNDARY = re.compile(r"\n\s*\n+")
_SPACES = re.compile(r"[ \t]+")
_SPACE_BEFORE_PUNCTUATION = re.compile(r"\s+([,.;:!?…])")
_MARKDOWN_LINK = re.compile(r"\[([^\]]+)\]\([^)]*\)")
_MARKDOWN_HEADING = re.compile(r"^\s{0,3}#{1,6}\s+", re.MULTILINE)
_MARKDOWN_MARKERS = re.compile(r"(\*\*|__|~~|`)")
_HTML_TAG = re.compile(r"</?[a-zA-Z][^>]*>")


@dataclass(frozen=True, slots=True)
class SpeechChunk:
    """A safe synthesis unit and the silence to append after it."""

    text: str
    pause_after_ms: int


def normalize_text(text: str) -> str:
    """Make model prose suitable for TTS without changing its meaning."""

    value = text.replace("\r\n", "\n").replace("\r", "\n")
    value = _MARKDOWN_LINK.sub(r"\1", value)
    value = _MARKDOWN_HEADING.sub("", value)
    value = _MARKDOWN_MARKERS.sub("", value)
    value = _HTML_TAG.sub("", value)
    lines = []
    for line in value.split("\n"):
        line = _SPACES.sub(" ", line).strip()
        line = _SPACE_BEFORE_PUNCTUATION.sub(r"\1", line)
        lines.append(line)
    value = "\n".join(lines)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip()


def split_for_speech(
    text: str,
    *,
    max_chars: int,
    sentence_pause_ms: int = 120,
    paragraph_pause_ms: int = 350,
) -> tuple[SpeechChunk, ...]:
    """Split normalized prose at sentence and paragraph boundaries."""

    if max_chars <= 0:
        raise ValueError("max_chars must be positive")
    if sentence_pause_ms < 0 or paragraph_pause_ms < 0:
        raise ValueError("pauses must not be negative")

    normalized = normalize_text(text)
    if not normalized:
        return ()

    chunks: list[SpeechChunk] = []
    paragraphs = [item.strip() for item in _PARAGRAPH_BOUNDARY.split(normalized)]
    for paragraph in paragraphs:
        if not paragraph:
            continue
        sentences = [item.strip() for item in _SENTENCE_BOUNDARY.split(paragraph)]
        sentence_units: list[tuple[str, int]] = []
        for sentence in sentences:
            if not sentence:
                continue
            parts = _split_long_sentence(sentence, max_chars)
            for index, part in enumerate(parts):
                pause = (
                    sentence_pause_ms if index < len(parts) - 1 else sentence_pause_ms
                )
                sentence_units.append((part, pause))
        if not sentence_units:
            continue
        # The last sentence of a paragraph gets a longer pause after packing.
        packed = _pack(sentence_units, max_chars)
        for index, (chunk_text, _) in enumerate(packed):
            is_last = index == len(packed) - 1
            chunks.append(
                SpeechChunk(
                    text=chunk_text,
                    pause_after_ms=paragraph_pause_ms if is_last else sentence_pause_ms,
                )
            )
    return tuple(chunks)


def _split_long_sentence(sentence: str, max_chars: int) -> list[str]:
    if len(sentence) <= max_chars:
        return [sentence]
    words = sentence.split()
    parts: list[str] = []
    current: list[str] = []
    for word in words:
        candidate = " ".join((*current, word))
        if current and len(candidate) > max_chars:
            parts.append(" ".join(current))
            current = [word]
        else:
            current.append(word)
    if current:
        parts.append(" ".join(current))
    # A single word longer than max_chars is split to keep every request bounded.
    bounded: list[str] = []
    for part in parts:
        if len(part) <= max_chars:
            bounded.append(part)
            continue
        bounded.extend(
            part[index : index + max_chars] for index in range(0, len(part), max_chars)
        )
    return bounded


def _pack(units: list[tuple[str, int]], max_chars: int) -> list[tuple[str, int]]:
    packed: list[tuple[str, int]] = []
    current: list[str] = []
    for unit, _ in units:
        candidate = " ".join((*current, unit))
        if current and len(candidate) > max_chars:
            packed.append((" ".join(current), 0))
            current = [unit]
        else:
            current.append(unit)
    if current:
        packed.append((" ".join(current), 0))
    return packed
