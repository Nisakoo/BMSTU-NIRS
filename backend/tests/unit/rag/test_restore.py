import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from io import StringIO
from pathlib import Path

import pytest

from smeshariki_ai.rag.cli import main
from smeshariki_ai.rag.memory import InMemoryKnowledgeStore
from smeshariki_ai.rag.models import (
    Artifact,
    Character,
    Continuity,
    EntityRef,
    EntityType,
    Episode,
    KnowledgeSet,
    Location,
    Work,
    entities_of,
    entity_ref,
)
from smeshariki_ai.rag.ports import (
    EntityChange,
    KnowledgeSnapshot,
    KnowledgeStore,
    LoadSummary,
    Revision,
)
from smeshariki_ai.rag.restore import restore_entity

NOW = datetime(2026, 11, 15, 12, 0, tzinfo=UTC)
EPISODE = EntityRef(type=EntityType.EPISODE, id="e1")
PIN = EntityRef(type=EntityType.CHARACTER, id="pin")


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


async def prepare(store: InMemoryKnowledgeStore) -> None:
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


async def save(
    store: InMemoryKnowledgeStore, entities: list, operation: str = "update"
) -> None:
    async with store.transaction() as transaction:
        load_id = await transaction.start_load(NOW)
        await transaction.save(
            load_id,
            [EntityChange(operation=operation, entity=entity) for entity in entities],
        )
        await transaction.finish_load(
            load_id,
            LoadSummary(finished_at=NOW, duration_ms=0, entity_count=0, counts={}),
        )


async def delete_episode(store: InMemoryKnowledgeStore) -> None:
    episode = next(e for e in knowledge().episodes if e.id == "e1")
    await save(store, [episode], "delete")


async def contents(store: InMemoryKnowledgeStore) -> KnowledgeSet:
    async with store.transaction() as transaction:
        return await transaction.read_all()


def memory(store: InMemoryKnowledgeStore):
    @asynccontextmanager
    async def factory() -> AsyncIterator[InMemoryKnowledgeStore]:
        yield store

    return factory


class StaticStore(KnowledgeStore):
    def __init__(self, value: KnowledgeSet, history: list[Revision]) -> None:
        self._value = value
        self._history = tuple(history)

    async def snapshot(self) -> KnowledgeSnapshot:
        return KnowledgeSnapshot(knowledge=self._value)

    async def revision_history(self, ref: EntityRef) -> tuple[Revision, ...]:
        return self._history

    @asynccontextmanager
    async def transaction(self):
        raise NotImplementedError
        yield  # pragma: no cover


def revision(number: int, payload: dict, format_version: int = 1) -> Revision:
    return Revision(
        revision=number,
        operation="create",
        load_id=1,
        format_version=format_version,
        payload=payload,
    )


async def test_dry_run_restores_a_deleted_entity_without_writing(
    tmp_path: Path,
) -> None:
    store = InMemoryKnowledgeStore()
    await prepare(store)
    await delete_episode(store)
    before = await contents(store)

    report = await restore_entity(EPISODE, store, apply=False)

    assert report.restored is False and report.issues == ()
    assert report.revision == 2
    assert report.counts["episodes"].added == 1
    assert report.entity_count == len(entities_of(before)) + 1
    assert await contents(store) == before
    async with store.transaction() as transaction:
        assert await transaction.read_load(3) is None


async def test_apply_restores_and_writes_a_revision() -> None:
    store = InMemoryKnowledgeStore()
    await prepare(store)
    await delete_episode(store)

    report = await restore_entity(EPISODE, store, apply=True)

    assert report.restored is True
    assert report.operation_id == 3
    assert report.revision == 2
    assert report.counts["episodes"].added == 1
    assert EPISODE in {
        entity_ref(entity) for entity in entities_of(await contents(store))
    }
    async with store.transaction() as transaction:
        load = await transaction.read_load(3)
        history = await transaction.read_revisions(EPISODE)
    assert load is not None and load.operation == "restore"
    assert [item.operation for item in history] == [
        "create",
        "delete",
        "create",
    ]


async def test_restores_an_older_revision() -> None:
    store = InMemoryKnowledgeStore()
    await prepare(store)
    pin = next(c for c in knowledge().characters if c.id == "pin")
    changed = pin.model_copy(update={"species": "птица"})
    await save(store, [changed])

    report = await restore_entity(PIN, store, revision=1, apply=True)

    assert report.restored is True
    assert report.revision == 1
    assert report.counts["characters"].updated == 1
    restored = next(c for c in (await contents(store)).characters if c.id == "pin")
    assert restored == pin
    async with store.transaction() as transaction:
        history = await transaction.read_revisions(PIN)
    assert [item.operation for item in history] == [
        "create",
        "update",
        "update",
    ]


async def test_missing_revision_is_rejected() -> None:
    store = InMemoryKnowledgeStore()
    await prepare(store)

    report = await restore_entity(PIN, store, revision=99, apply=True)

    assert report.restored is False
    assert [issue.code for issue in report.issues] == ["revision_not_found"]


async def test_no_history_is_rejected() -> None:
    store = InMemoryKnowledgeStore()
    await prepare(store)

    report = await restore_entity(
        EntityRef(type=EntityType.CHARACTER, id="ghost"), store, apply=False
    )

    assert report.restored is False
    assert [issue.code for issue in report.issues] == ["revision_not_found"]


async def test_invalid_payload_is_rejected() -> None:
    store = StaticStore(KnowledgeSet(), [revision(1, {"id": "e1"})])

    report = await restore_entity(EPISODE, store, apply=False)

    assert report.restored is False
    assert [issue.code for issue in report.issues] == ["revision_invalid"]


async def test_unsupported_format_is_rejected() -> None:
    payload = Episode.model_validate(
        {"id": "e1", "work": "series", "number": 1, "title": "Серия"}
    ).model_dump(mode="json", by_alias=True)
    store = StaticStore(KnowledgeSet(), [revision(1, payload, 999)])

    report = await restore_entity(EPISODE, store, apply=False)

    assert report.restored is False
    assert [issue.code for issue in report.issues] == ["unsupported_revision_format"]


async def test_missing_references_are_rejected() -> None:
    payload = Episode.model_validate(
        {"id": "e1", "work": "series", "number": 1, "title": "Серия"}
    ).model_dump(mode="json", by_alias=True)
    store = StaticStore(KnowledgeSet(), [revision(1, payload)])

    report = await restore_entity(EPISODE, store, apply=False)

    assert report.restored is False
    assert [issue.code for issue in report.issues] == ["unknown_reference"]


async def test_unchanged_snapshot_only_journals_the_restore() -> None:
    store = InMemoryKnowledgeStore()
    await prepare(store)

    report = await restore_entity(PIN, store, apply=True)

    assert report.restored is True
    assert report.counts["characters"].unchanged == 1
    async with store.transaction() as transaction:
        history = await transaction.read_revisions(PIN)
        load = await transaction.read_load(2)
    assert [item.revision for item in history] == [1]
    assert load is not None and load.operation == "restore"


async def test_restore_logs_only_safe_fields(
    caplog: pytest.LogCaptureFixture,
) -> None:
    store = InMemoryKnowledgeStore()
    await prepare(store)
    await delete_episode(store)
    caplog.set_level("INFO", logger="smeshariki_ai.rag.restore")

    await restore_entity(EPISODE, store, apply=True)

    record = next(r for r in caplog.records if r.event == "rag.restore.completed")
    assert record.outcome == "restored"
    assert record.entity_count == len(entities_of(knowledge()))
    assert "e1" not in str(record.log_fields)


def test_cli_dry_run_and_apply() -> None:
    import asyncio

    store = InMemoryKnowledgeStore()
    asyncio.run(prepare(store))
    asyncio.run(delete_episode(store))

    output = StringIO()
    code = main(["restore", "episodes/e1"], stdout=output, store=memory(store))

    assert code == 0
    assert "Будет восстановлено." in output.getvalue()

    output = StringIO()
    code = main(
        ["restore", "episodes/e1", "--apply", "--format", "json"],
        stdout=output,
        store=memory(store),
    )

    report = json.loads(output.getvalue())
    assert code == 0
    assert report["restored"] is True
    assert report["revision"] == 2
    assert report["counts"]["episodes"]["added"] == 1


def test_cli_rejects_bad_revision_and_reference(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["restore", "characters/pin", "--revision", "0"]) == 2
    assert "usage" in capsys.readouterr().err
    assert main(["restore", "heroes/pin"]) == 2
    assert "usage" in capsys.readouterr().err
