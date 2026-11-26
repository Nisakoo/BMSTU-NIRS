from __future__ import annotations

from pathlib import Path

from smeshariki_ai.rag.lore.cleanup import (
    RULES,
    clean_package,
    clean_text,
    normalize_whitespace,
    remove_urls,
)
from smeshariki_ai.rag.lore.package import check_package
from smeshariki_ai.rag.yaml_reader import read_yaml_file

URL = "https://youtu.be/9IsFUwqf188"


def write_package(root: Path, *, text: str, document_id: str = "d01") -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "package.yaml").write_text("format_version: 1\n", encoding="utf-8")
    documents = root / "documents"
    documents.mkdir(exist_ok=True)
    path = documents / f"{document_id}.yaml"
    body = text.replace("\\n", "\n")
    path.write_text(
        f"id: {document_id}\n"
        f"title: Эпизод\n"
        f"text: |\n"
        + "".join(f"  {line}\n" for line in body.splitlines())
        + "source: Эпизод.txt\n"
        "continuity: classic\n"
        "characters:\n"
        "- krosh\n"
        "tags:\n"
        "- plot\n",
        encoding="utf-8",
    )
    return path


def test_url_line_is_removed_by_the_rule() -> None:
    cleaned, removed = remove_urls(f"{URL}\n\nПорай.\n\nИ наконец о погоде.")

    assert removed == 1
    assert "http" not in cleaned
    assert cleaned.lstrip().startswith("Порай.")
    assert "И наконец о погоде." in cleaned
    # The whitespace rule removes the blank line the deletion left behind.
    assert clean_text(f"{URL}\n\nПорай.")[0] == "Порай."


def test_inline_leading_url_is_removed() -> None:
    cleaned, removed = remove_urls(f"{URL} Порай.")

    assert removed == 1
    assert cleaned == "Порай."


def test_rule_keeps_style_times_ellipses_and_duplicates() -> None:
    text = (
        "Ха-ха-ха! Бац-бац-бац.\n\n"
        "Встречаемся в 9:00 утра...\n\n"
        "Спорим.\n\n"
        "Спорим.\n\n"
        "Ёжик!"
    )

    cleaned, removed = remove_urls(text)

    assert removed == 0
    assert cleaned == text


def test_whitespace_rule_is_conservative() -> None:
    cleaned, removed = normalize_whitespace("  Первая.  \n\n\n\nВторая.  ")

    assert removed == 0
    assert cleaned == "Первая.\n\nВторая."


def test_rules_are_named_and_ordered() -> None:
    assert [rule.name for rule in RULES] == ["url_lines", "whitespace"]


def test_clean_text_combines_the_rules() -> None:
    cleaned, removed = clean_text(f"{URL}\n\n  Текст.  \n\n\n\nЕщё.")

    assert removed == 1
    assert cleaned == "Текст.\n\nЕщё."


def test_dry_run_reports_but_does_not_write(tmp_path: Path) -> None:
    root = tmp_path / "lore"
    path = write_package(root, text=f"{URL}\n\nПорай.")
    before = path.read_text(encoding="utf-8")

    report = clean_package(root)

    assert report.applied is False
    assert report.document_count == 1
    assert report.changed_count == 1
    assert report.removed_lines == 1
    assert report.removed_chars > 0
    assert report.backup_path is None
    assert path.read_text(encoding="utf-8") == before


def test_apply_rewrites_text_and_creates_a_backup(tmp_path: Path) -> None:
    root = tmp_path / "lore"
    path = write_package(root, text=f"{URL}\n\nПорай.\n\nЕщё реплика.")

    report = clean_package(root, apply=True)

    assert report.applied is True
    assert report.backup_path is not None
    backup = Path(report.backup_path) / "documents" / "d01.yaml"
    assert backup.is_file()
    assert URL in backup.read_text(encoding="utf-8")

    document = read_yaml_file(path)
    assert URL not in str(document["text"])
    assert document["title"] == "Эпизод"
    assert document["source"] == "Эпизод.txt"
    assert document["continuity"] == "classic"
    assert document["characters"] == ["krosh"]
    assert document["tags"] == ["plot"]
    assert check_package(root).valid is True


def test_apply_is_idempotent(tmp_path: Path) -> None:
    root = tmp_path / "lore"
    write_package(root, text=f"{URL}\n\nПорай.")
    clean_package(root, apply=True)
    first = (root / "documents" / "d01.yaml").read_text(encoding="utf-8")

    second_report = clean_package(root, apply=True)

    assert second_report.changed_count == 0
    assert second_report.backup_path is None
    assert (root / "documents" / "d01.yaml").read_text(encoding="utf-8") == first


def test_clean_package_keeps_texts_without_noise(tmp_path: Path) -> None:
    root = tmp_path / "lore"
    path = write_package(root, text="Ха-ха-ха! В 9:00 утра...")
    before = path.read_text(encoding="utf-8")

    report = clean_package(root, apply=True)

    assert report.changed_count == 0
    assert path.read_text(encoding="utf-8") == before


def test_invalid_package_is_reported_and_not_written(tmp_path: Path) -> None:
    root = tmp_path / "lore"
    root.mkdir()

    report = clean_package(root, apply=True)

    assert report.applied is False
    assert report.issues
    assert report.issues[0].code == "missing_manifest"
