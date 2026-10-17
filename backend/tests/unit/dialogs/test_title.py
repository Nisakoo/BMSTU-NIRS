import pytest

from smeshariki_ai.dialogs import make_title


def test_title_keeps_short_text() -> None:
    assert make_title("Привет, Крош!") == "Привет, Крош!"


def test_title_trims_and_collapses_whitespace() -> None:
    assert make_title("  first\n\n\tsecond   third \n") == "first second third"


def test_title_keeps_exactly_sixty_characters() -> None:
    text = "a" * 60

    assert make_title(text) == text


def test_title_truncates_sixty_one_characters_with_ellipsis() -> None:
    assert make_title("a" * 61) == "a" * 60 + "…"


def test_title_counts_code_points_of_non_ascii_text() -> None:
    title = make_title("Ё" * 100)

    assert title == "Ё" * 60 + "…"
    assert len(title) == 61


def test_title_is_normalized_before_truncation() -> None:
    text = ("word \n" * 30).strip()

    title = make_title(text)

    assert title == "word " * 12 + "…"


@pytest.mark.parametrize("text", ["", "   \n\t"])
def test_title_of_blank_text_is_empty(text: str) -> None:
    assert make_title(text) == ""
