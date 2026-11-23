from __future__ import annotations

from pathlib import Path

from smeshariki_ai.rag.lore.package import (
    check_package,
    read_package,
)


def write_package(root: Path, documents: dict[str, str]) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "package.yaml").write_text("format_version: 1\n", encoding="utf-8")
    documents_dir = root / "documents"
    documents_dir.mkdir(exist_ok=True)
    for name, text in documents.items():
        (documents_dir / f"{name}.yaml").write_text(text, encoding="utf-8")


def document(text: str = "Крош и Ёжик пошли гулять.") -> str:
    return (
        "id: d01\n"
        "title: Прогулка\n"
        "text: |\n"
        f"  {text}\n"
        "source: Синтетический сценарий\n"
        "continuity: classic\n"
        "characters: [krosh, ezhik]\n"
        "tags: [дружба]\n"
    )


def test_valid_package_is_read_and_checked(tmp_path: Path) -> None:
    write_package(tmp_path, {"d01": document()})

    report = check_package(tmp_path)
    contents = read_package(tmp_path)

    assert report.valid is True
    assert report.document_count == 1
    assert len(contents.documents) == 1
    assert contents.documents[0].id == "d01"
    assert contents.documents[0].characters == ("krosh", "ezhik")


def test_missing_manifest_is_reported(tmp_path: Path) -> None:
    (tmp_path / "documents").mkdir()
    report = check_package(tmp_path)
    assert report.valid is False
    assert report.issues[0].code == "missing_manifest"


def test_missing_documents_directory_is_reported(tmp_path: Path) -> None:
    (tmp_path / "package.yaml").write_text("format_version: 1\n", encoding="utf-8")
    report = check_package(tmp_path)
    assert report.valid is False
    assert report.issues[0].code == "missing_documents_directory"


def test_id_must_match_the_file_name(tmp_path: Path) -> None:
    write_package(tmp_path, {"other": document()})
    report = check_package(tmp_path)
    assert report.valid is False
    assert report.issues[0].code == "file_id_mismatch"


def test_missing_required_field_is_reported(tmp_path: Path) -> None:
    write_package(
        tmp_path,
        {"d01": "id: d01\ntext: |\n  Без заголовка.\n"},
    )
    report = check_package(tmp_path)
    assert report.valid is False
    assert report.issues[0].code == "missing_field"
    assert report.issues[0].path == "title"


def test_unexpected_file_is_reported(tmp_path: Path) -> None:
    write_package(tmp_path, {"d01": document()})
    (tmp_path / "notes.txt").write_text("лишнее", encoding="utf-8")
    report = check_package(tmp_path)
    assert report.valid is False
    assert any(issue.code == "unexpected_file" for issue in report.issues)


def test_symlink_is_rejected_without_reading(tmp_path: Path) -> None:
    write_package(tmp_path, {"d01": document()})
    (tmp_path / "documents" / "link.yaml").symlink_to(
        tmp_path / "documents" / "d01.yaml"
    )
    report = check_package(tmp_path)
    assert report.valid is False
    assert any(issue.code == "symlink_not_allowed" for issue in report.issues)


def test_unsupported_format_version_is_reported(tmp_path: Path) -> None:
    write_package(tmp_path, {"d01": document()})
    (tmp_path / "package.yaml").write_text("format_version: 2\n", encoding="utf-8")
    report = check_package(tmp_path)
    assert report.valid is False
    assert report.issues[0].code == "unsupported_format_version"


def test_yaml_duplicate_key_is_reported(tmp_path: Path) -> None:
    write_package(
        tmp_path,
        {"d01": "id: d01\ntitle: Первый\ntitle: Второй\ntext: |\n  Текст.\n"},
    )
    report = check_package(tmp_path)
    assert report.valid is False
    assert report.issues[0].code == "duplicate_key"
