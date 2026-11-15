import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from io import StringIO
from pathlib import Path

import pytest

from smeshariki_ai.rag.cli import main
from smeshariki_ai.rag.maintenance import delete_entities
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
    KnowledgeStoreUnavailableError,
    LoadSummary,
)

NOW = datetime(2026, 11, 15, 12, 0, tzinfo=UTC)
PIN = EntityRef(type=EntityType.CHARACTER, id="pin")
EPISODE = EntityRef(type=EntityType.EPISODE, id="e1")


def version() -> dict:
    return {
        "continuities": ["classic"],
        "age_group": "adult",
        "traits": ["изобретательный"],
        "speech_style": {"register": "разговорный"},
    }


def character(entity_id: str, name: str, target: str | None = None) -> Character:
    relationships = (
        [{"to": target, "type": "friendship", "continuities": ["classic"]}]
        if target
        else []
    )
    return Character.model_validate(
        {
            "id": entity_id,
            "name": name,
            "species": "пингвин",
            "versions": [version()],
            "relationships": relationships,
        }
    )


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
        characters=(character("pin", "Пин"),),
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


async def prepare(
    store: InMemoryKnowledgeStore, value: KnowledgeSet | None = None
) -> None:
    async with store.transaction() as transaction:
        load_id = await transaction.start_load(NOW)
        await transaction.save(
            load_id,
            [
                EntityChange(operation="create", entity=entity)
                for entity in entities_of(value or knowledge())
            ],
        )
        await transaction.finish_load(
            load_id,
            LoadSummary(finished_at=NOW, duration_ms=0, entity_count=0, counts={}),
        )


async def contents(store: InMemoryKnowledgeStore) -> KnowledgeSet:
    async with store.transaction() as transaction:
        return await transaction.read_all()


def memory(store: InMemoryKnowledgeStore):
    @asynccontextmanager
    async def factory() -> AsyncIterator[InMemoryKnowledgeStore]:
        yield store

    return factory


async def test_dry_run_changes_nothing(tmp_path: Path) -> None:
    store = InMemoryKnowledgeStore()
    await prepare(store)
    before = await contents(store)

    report = await delete_entities([EPISODE], store, apply=False)

    assert report.applied is False and report.issues == ()
    assert report.counts["episodes"].deleted == 1
    assert report.entity_count == len(entities_of(before)) - 1
    assert await contents(store) == before
    async with store.transaction() as transaction:
        assert await transaction.read_load(2) is None
        assert [
            revision.operation for revision in await transaction.read_revisions(EPISODE)
        ] == ["create"]


async def test_apply_deletes_revisions_and_journals(tmp_path: Path) -> None:
    store = InMemoryKnowledgeStore()
    await prepare(store)

    report = await delete_entities([EPISODE], store, apply=True)

    assert report.applied is True
    assert report.operation_id == 2
    assert report.issues == ()
    assert report.counts["episodes"].deleted == 1
    assert EPISODE not in {entity_ref(e) for e in entities_of(await contents(store))}
    async with store.transaction() as transaction:
        load = await transaction.read_load(2)
        history = await transaction.read_revisions(EPISODE)
    assert load is not None and load.operation == "delete"
    assert load.summary is not None
    assert load.summary.counts["episodes"].deleted == 1
    assert [revision.operation for revision in history] == ["create", "delete"]
    assert Episode.model_validate(history[-1].payload).id == "e1"


async def test_referenced_entity_is_rejected(tmp_path: Path) -> None:
    store = InMemoryKnowledgeStore()
    await prepare(store)
    before = await contents(store)

    report = await delete_entities([PIN], store, apply=True)

    assert report.applied is False
    assert {(issue.file, issue.code) for issue in report.issues} >= {
        ("db:episodes/e1", "unknown_reference")
    }
    assert all(issue.code == "unknown_reference" for issue in report.issues)
    assert await contents(store) == before
    async with store.transaction() as transaction:
        assert await transaction.read_load(2) is None


async def test_dependent_entity_can_be_deleted_together() -> None:
    store = InMemoryKnowledgeStore()
    await prepare(store)
    episode = EntityRef(type=EntityType.EPISODE, id="e1")

    report = await delete_entities(
        [
            episode,
            PIN,
            EntityRef(type=EntityType.LOCATION, id="house"),
            EntityRef(type=EntityType.ARTIFACT, id="plane"),
        ],
        store,
        apply=True,
    )

    assert report.applied is True
    assert report.issues == ()
    assert report.counts["episodes"].deleted == 1
    assert report.counts["characters"].deleted == 1
    assert report.counts["locations"].deleted == 1
    assert report.counts["artifacts"].deleted == 1
    stored = await contents(store)
    assert stored.episodes == ()
    assert stored.characters == ()
    assert stored.locations == ()
    assert stored.artifacts == ()


async def test_mutually_related_characters_are_deleted_together() -> None:
    pin = character("pin", "Пин", target="krosh")
    krosh = character("krosh", "Крош", target="pin")
    store = InMemoryKnowledgeStore()
    await prepare(
        store,
        KnowledgeSet(
            continuities=(Continuity(id="classic", name="Классика"),),
            characters=(pin, krosh),
        ),
    )

    report = await delete_entities(
        [
            EntityRef(type=EntityType.CHARACTER, id="pin"),
            EntityRef(type=EntityType.CHARACTER, id="krosh"),
        ],
        store,
        apply=True,
    )

    assert report.applied is True
    assert report.issues == ()
    assert report.counts["characters"].deleted == 2
    assert await contents(store) == KnowledgeSet(
        continuities=(Continuity(id="classic", name="Классика"),)
    )


async def test_missing_entity_is_an_error() -> None:
    store = InMemoryKnowledgeStore()
    await prepare(store)

    report = await delete_entities(
        [EntityRef(type=EntityType.CHARACTER, id="ghost")], store, apply=True
    )

    assert report.applied is False
    assert [issue.code for issue in report.issues] == ["entity_not_found"]


async def test_store_failure_is_safe() -> None:
    class BrokenStore(InMemoryKnowledgeStore):
        async def snapshot(self):  # type: ignore[override]
            raise KnowledgeStoreUnavailableError

        @asynccontextmanager
        async def transaction(self):  # type: ignore[override]
            raise KnowledgeStoreUnavailableError
            yield  # pragma: no cover

    report = await delete_entities(
        [EntityRef(type=EntityType.LOCATION, id="house")],
        BrokenStore(),
        apply=False,
    )

    assert report.applied is False
    assert [issue.code for issue in report.issues] == ["database_unavailable"]


async def test_delete_logs_only_safe_fields(
    caplog: pytest.LogCaptureFixture,
) -> None:
    store = InMemoryKnowledgeStore()
    await prepare(store)
    caplog.set_level("INFO", logger="smeshariki_ai.rag.maintenance")

    await delete_entities([EPISODE], store, apply=True)

    record = next(r for r in caplog.records if r.event == "rag.delete.completed")
    assert record.outcome == "applied"
    assert record.deleted_count == 1
    assert "e1" not in str(record.log_fields)


def test_cli_dry_run_and_apply() -> None:
    import asyncio

    store = InMemoryKnowledgeStore()
    asyncio.run(prepare(store))

    output = StringIO()
    code = main(
        ["delete", "episodes/e1"],
        stdout=output,
        store=memory(store),
    )

    assert code == 0
    assert "Будет удалено." in output.getvalue()

    output = StringIO()
    code = main(
        ["delete", "episodes/e1", "--apply"],
        stdout=output,
        store=memory(store),
    )

    assert code == 0
    assert "Удаление выполнено." in output.getvalue()


def test_cli_rejects_bad_reference_and_reports_missing(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["delete", "heroes/pin"], stdout=StringIO()) == 2
    assert "usage" in capsys.readouterr().err

    import asyncio

    store = InMemoryKnowledgeStore()
    asyncio.run(prepare(store))
    output = StringIO()
    code = main(
        ["delete", "characters/ghost", "--apply"],
        stdout=output,
        store=memory(store),
    )

    assert code == 1
    assert "[entity_not_found]" in output.getvalue()


def test_cli_json_report() -> None:
    import asyncio

    store = InMemoryKnowledgeStore()
    asyncio.run(prepare(store))
    output = StringIO()

    code = main(
        ["delete", "episodes/e1", "--apply", "--format", "json"],
        stdout=output,
        store=memory(store),
    )

    report = json.loads(output.getvalue())
    assert code == 0
    assert report["applied"] is True
    assert report["counts"]["episodes"]["deleted"] == 1
    assert report["operation_id"] == 2
