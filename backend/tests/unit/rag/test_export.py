from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from io import StringIO
from pathlib import Path

import pytest
import yaml

from smeshariki_ai.rag.cli import main
from smeshariki_ai.rag.maintenance import export_package
from smeshariki_ai.rag.memory import InMemoryKnowledgeStore
from smeshariki_ai.rag.models import (
    Artifact,
    Character,
    Continuity,
    EntityType,
    Episode,
    KnowledgeSet,
    Location,
    Work,
    entities_of,
)
from smeshariki_ai.rag.package import read_package
from smeshariki_ai.rag.ports import (
    EntityChange,
    KnowledgeStoreUnavailableError,
    LoadSummary,
)
from smeshariki_ai.rag.services import check_package

NOW = datetime(2026, 11, 15, 12, 0, tzinfo=UTC)


def version() -> dict:
    return {
        "continuities": ["classic"],
        "age_group": "adult",
        "traits": ["изобретательный"],
        "speech_style": {"register": "разговорный"},
    }


def knowledge() -> KnowledgeSet:
    return KnowledgeSet(
        continuities=(Continuity(id="classic", name="Классика"),),
        works=(
            Work.model_validate(
                {
                    "id": "series",
                    "title": "Сериал",
                    "kind": "series",
                    "continuity": "classic",
                }
            ),
        ),
        episodes=(
            Episode.model_validate(
                {
                    "id": "e1",
                    "work": "series",
                    "season": 1,
                    "number": 1,
                    "title": "Серия",
                    "characters": ["pin"],
                    "locations": ["house"],
                    "artifacts": ["plane"],
                }
            ),
        ),
        characters=(
            Character.model_validate(
                {
                    "id": "pin",
                    "name": "Пин",
                    "aliases": ["Механик"],
                    "species": "пингвин",
                    "versions": [version()],
                }
            ),
        ),
        locations=(
            Location.model_validate(
                {
                    "id": "house",
                    "name": "Дом",
                    "description": "Дом.",
                    "continuities": ["classic"],
                    "residents": ["pin"],
                }
            ),
        ),
        artifacts=(
            Artifact.model_validate(
                {
                    "id": "plane",
                    "name": "Самолёт",
                    "artifact_type": "машина",
                    "description": "Летает.",
                    "continuities": ["classic"],
                    "creators": ["pin"],
                }
            ),
        ),
    )


async def stored(store: InMemoryKnowledgeStore) -> None:
    async with store.transaction() as transaction:
        load_id = await transaction.start_load(NOW)
        await transaction.save(
            load_id,
            [
                EntityChange(operation="create", entity=entity)
                for entity in entities_of(knowledge())
            ],
        )
        await transaction.finish_load(
            load_id,
            LoadSummary(finished_at=NOW, duration_ms=0, entity_count=0, counts={}),
        )


def memory(store: InMemoryKnowledgeStore):
    @asynccontextmanager
    async def factory() -> AsyncIterator[InMemoryKnowledgeStore]:
        yield store

    return factory


def assert_no_null(path: Path) -> None:
    for file in path.rglob("*.yaml"):
        assert "null" not in file.read_text(encoding="utf-8")


async def test_export_writes_a_valid_package_and_round_trips(tmp_path: Path) -> None:
    store = InMemoryKnowledgeStore()
    await stored(store)
    root = tmp_path / "export"

    report = await export_package(root, store)

    assert report.exported is True and report.issues == ()
    assert report.entity_count == len(entities_of(knowledge()))
    contents = read_package(root)
    assert contents.issues == ()
    assert contents.knowledge == knowledge()
    assert check_package(root).valid
    manifest = yaml.safe_load((root / "package.yaml").read_text(encoding="utf-8"))
    assert manifest["format_version"] == 1
    assert manifest["revisions"]["characters"] == {"pin": 1}
    assert manifest["revisions"]["episodes"] == {"e1": 1}
    assert_no_null(root)


async def test_existing_empty_directory_is_written_in_place(tmp_path: Path) -> None:
    store = InMemoryKnowledgeStore()
    await stored(store)
    root = tmp_path / "export"
    root.mkdir()

    report = await export_package(root, store)

    assert report.exported is True
    assert (root / "package.yaml").is_file()
    assert (root / "characters" / "pin.yaml").is_file()


async def test_type_filter_exports_only_selected_type(tmp_path: Path) -> None:
    store = InMemoryKnowledgeStore()
    await stored(store)
    root = tmp_path / "export"

    report = await export_package(root, store, [EntityType.CHARACTER])

    assert report.exported is True
    assert report.counts["characters"] == 1
    assert report.counts["episodes"] == 0
    contents = read_package(root)
    assert contents.knowledge.characters == knowledge().characters
    assert contents.knowledge.episodes == ()
    assert check_package(root).valid


async def test_empty_store_is_an_error(tmp_path: Path) -> None:
    report = await export_package(tmp_path / "export", InMemoryKnowledgeStore())

    assert report.exported is False
    assert [issue.code for issue in report.issues] == ["empty_store"]
    assert not (tmp_path / "export").exists()


async def test_empty_selection_is_an_error(tmp_path: Path) -> None:
    store = InMemoryKnowledgeStore()
    async with store.transaction() as transaction:
        load_id = await transaction.start_load(NOW)
        await transaction.save(
            load_id,
            [
                EntityChange(
                    operation="create",
                    entity=Continuity(id="classic", name="Классика"),
                )
            ],
        )
        await transaction.finish_load(
            load_id,
            LoadSummary(finished_at=NOW, duration_ms=0, entity_count=0, counts={}),
        )

    report = await export_package(tmp_path / "export", store, [EntityType.CHARACTER])

    assert report.exported is False
    assert [issue.code for issue in report.issues] == ["empty_selection"]


async def test_non_empty_destination_is_rejected(tmp_path: Path) -> None:
    store = InMemoryKnowledgeStore()
    await stored(store)
    root = tmp_path / "export"
    root.mkdir()
    marker = root / "keep.txt"
    marker.write_text("keep", encoding="utf-8")

    report = await export_package(root, store)

    assert report.exported is False
    assert [issue.code for issue in report.issues] == ["destination_not_empty"]
    assert marker.read_text(encoding="utf-8") == "keep"


async def test_store_failure_is_safe_and_writes_nothing(tmp_path: Path) -> None:
    class BrokenStore(InMemoryKnowledgeStore):
        async def snapshot(self):  # type: ignore[override]
            raise KnowledgeStoreUnavailableError

    report = await export_package(tmp_path / "export", BrokenStore())

    assert report.exported is False
    assert [issue.code for issue in report.issues] == ["database_unavailable"]
    assert not (tmp_path / "export").exists()


async def test_write_failure_leaves_no_partial_package(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = InMemoryKnowledgeStore()
    await stored(store)

    def fail(*args, **kwargs) -> None:
        raise OSError("disk full")

    monkeypatch.setattr("smeshariki_ai.rag.maintenance.write_package", fail)

    report = await export_package(tmp_path / "export", store)

    assert report.exported is False
    assert [issue.code for issue in report.issues] == ["export_failed"]
    assert not (tmp_path / "export").exists()
    assert not list(tmp_path.glob(".export-*"))


async def test_write_failure_cleans_existing_empty_destination(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = InMemoryKnowledgeStore()
    await stored(store)
    root = tmp_path / "export"
    root.mkdir()

    def fail(destination, *args, **kwargs) -> None:
        (destination / "partial.yaml").write_text("x", encoding="utf-8")
        raise OSError("disk full")

    monkeypatch.setattr("smeshariki_ai.rag.maintenance.write_package", fail)

    report = await export_package(root, store)

    assert report.exported is False
    assert [issue.code for issue in report.issues] == ["export_failed"]
    assert list(root.iterdir()) == []


async def test_export_logs_only_safe_fields(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    store = InMemoryKnowledgeStore()
    await stored(store)
    caplog.set_level("INFO", logger="smeshariki_ai.rag.maintenance")

    await export_package(tmp_path / "export", store)

    record = next(r for r in caplog.records if r.event == "rag.export.completed")
    assert record.outcome == "exported"
    assert record.entity_count == len(entities_of(knowledge()))
    assert "path" not in record.log_fields
    assert "pin" not in str(record.log_fields)


def test_cli_export_text_and_json(tmp_path: Path) -> None:
    store = InMemoryKnowledgeStore()

    async def prepare() -> None:
        await stored(store)

    import asyncio

    asyncio.run(prepare())
    output = StringIO()
    code = main(
        ["export", str(tmp_path / "export")], stdout=output, store=memory(store)
    )

    assert code == 0
    assert "Экспортировано сущностей" in output.getvalue()

    output = StringIO()
    code = main(
        ["export", str(tmp_path / "json"), "--format", "json"],
        stdout=output,
        store=memory(store),
    )

    import json

    report = json.loads(output.getvalue())
    assert code == 0
    assert report["exported"] is True
    assert report["counts"]["characters"] == 1


def test_cli_export_rejects_unknown_type_and_non_empty_destination(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["export", str(tmp_path), "--type", "heroes"], stdout=StringIO()) == 2
    assert "usage" in capsys.readouterr().err

    store = InMemoryKnowledgeStore()
    root = tmp_path / "export"
    root.mkdir()
    (root / "keep").write_text("x", encoding="utf-8")
    output = StringIO()

    assert main(["export", str(root)], stdout=output, store=memory(store)) == 1
    assert "[destination_not_empty]" in output.getvalue()
