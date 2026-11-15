from collections.abc import AsyncIterator, Callable, Iterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import yaml

from smeshariki_ai.rag.memory import InMemoryKnowledgeStore
from smeshariki_ai.rag.models import (
    Character,
    CharacterVersion,
    Continuity,
    Episode,
    KnowledgeEntity,
    KnowledgeSet,
    Work,
    entity_ref,
)
from smeshariki_ai.rag.package import entity_file
from smeshariki_ai.rag.ports import (
    EntityChange,
    KnowledgeDataInvalidError,
    KnowledgeSchemaNotReadyError,
    KnowledgeStore,
    KnowledgeStoreUnavailableError,
    KnowledgeTransaction,
    LoadSummary,
)
from smeshariki_ai.rag.services import load_package

START = datetime(2026, 10, 19, 12, 0, tzinfo=UTC)


def version(*continuities: str) -> dict:
    return {
        "continuities": list(continuities),
        "age_group": "adult",
        "traits": ["изобретательный"],
        "speech_style": {"register": "разговорный"},
    }


CLASSIC = Continuity(id="classic", name="Классика")
MOVIES = Continuity(id="movies", name="Фильмы")
SERIES = Work.model_validate(
    {"id": "series", "title": "Сериал", "kind": "series", "continuity": "classic"}
)
FILM = Work.model_validate(
    {"id": "film", "title": "Фильм", "kind": "film", "continuity": "movies"}
)
PIN = Character.model_validate(
    {
        "id": "pin",
        "name": "Пин",
        "species": "пингвин",
        "versions": [version("classic", "movies")],
    }
)
KROSH = Character.model_validate(
    {
        "id": "krosh",
        "name": "Крош",
        "species": "кролик",
        "versions": [version("classic")],
    }
)
FILM_EPISODE = Episode.model_validate(
    {
        "id": "film_main",
        "work": "film",
        "number": 1,
        "title": "Фильм",
        "characters": ["pin"],
    }
)
BASE: list[KnowledgeEntity] = [CLASSIC, MOVIES, SERIES, FILM, PIN, KROSH, FILM_EPISODE]


def write_package(
    root: Path,
    entities: list[KnowledgeEntity],
    revisions: dict[str, dict[str, int]] | None = None,
) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    manifest = {"format_version": 1}
    if revisions:
        manifest["revisions"] = revisions
    (root / "package.yaml").write_text(
        yaml.safe_dump(manifest, allow_unicode=True), encoding="utf-8"
    )
    for entity in entities:
        path = root / entity_file(entity_ref(entity))
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = entity.model_dump(mode="json", by_alias=True)
        path.write_text(yaml.safe_dump(payload, allow_unicode=True), encoding="utf-8")
    return root


def clock() -> Iterator[datetime]:
    moment = START
    while True:
        yield moment
        moment += timedelta(milliseconds=250)


def ticking() -> Callable[[], datetime]:
    ticks = clock()
    return lambda: next(ticks)


async def stored(store: KnowledgeStore) -> KnowledgeSet:
    async with store.transaction() as transaction:
        return await transaction.read_all()


@pytest.fixture
def store() -> InMemoryKnowledgeStore:
    return InMemoryKnowledgeStore()


async def test_invalid_package_does_not_touch_the_store(
    tmp_path: Path, store: InMemoryKnowledgeStore
) -> None:
    write_package(tmp_path, [])
    (tmp_path / "characters").mkdir()
    (tmp_path / "characters" / "pin.yaml").write_text("id: pin\n", encoding="utf-8")

    report = await load_package(tmp_path, store, ticking())

    assert report.loaded is False
    assert {issue.code for issue in report.issues} == {"missing_field"}
    assert report.load_id is None
    assert await stored(store) == KnowledgeSet()
    async with store.transaction() as transaction:
        assert await transaction.read_load(1) is None


async def test_first_load_adds_everything(
    tmp_path: Path, store: InMemoryKnowledgeStore
) -> None:
    report = await load_package(write_package(tmp_path, BASE), store, ticking())

    assert report.loaded is True and report.issues == ()
    assert report.counts["characters"].added == 2
    assert report.counts["episodes"].added == 1
    assert report.entity_count == len(BASE)
    assert report.duration_ms == 250
    knowledge = await stored(store)
    assert set(knowledge.characters) == {PIN, KROSH}
    async with store.transaction() as transaction:
        load = await transaction.read_load(report.load_id)
        revisions = await transaction.read_revisions(entity_ref(PIN))
    assert load is not None and load.summary is not None
    assert load.summary.entity_count == len(BASE)
    assert load.summary.counts["characters"].added == 2
    assert [revision.operation for revision in revisions] == ["create"]


async def test_reloading_the_same_package_changes_nothing(
    tmp_path: Path, store: InMemoryKnowledgeStore
) -> None:
    root = write_package(tmp_path, BASE)
    await load_package(root, store, ticking())
    before = await stored(store)

    report = await load_package(root, store, ticking())

    assert report.loaded is True
    assert all(counts.added == counts.updated == 0 for counts in report.counts.values())
    assert sum(counts.unchanged for counts in report.counts.values()) == len(BASE)
    assert await stored(store) == before
    async with store.transaction() as transaction:
        assert len(await transaction.read_revisions(entity_ref(PIN))) == 1
        assert await transaction.read_load(report.load_id) is not None


async def test_changed_entity_is_updated_and_others_kept(
    tmp_path: Path, store: InMemoryKnowledgeStore
) -> None:
    await load_package(write_package(tmp_path / "a", BASE), store, ticking())
    changed = KROSH.model_copy(update={"species": "заяц"})

    report = await load_package(
        write_package(tmp_path / "b", [changed]), store, ticking()
    )

    assert report.counts["characters"].updated == 1
    knowledge = await stored(store)
    assert set(knowledge.characters) == {PIN, changed}
    assert knowledge.episodes == (FILM_EPISODE,)
    async with store.transaction() as transaction:
        history = await transaction.read_revisions(entity_ref(KROSH))
    assert [revision.operation for revision in history] == ["create", "update"]


async def test_partial_package_relies_on_stored_entities(
    tmp_path: Path, store: InMemoryKnowledgeStore
) -> None:
    await load_package(write_package(tmp_path / "a", BASE), store, ticking())
    episode = Episode.model_validate(
        {
            "id": "s01e01",
            "work": "series",
            "number": 1,
            "title": "Серия",
            "characters": ["krosh", "pin"],
        }
    )

    report = await load_package(
        write_package(tmp_path / "b", [episode]), store, ticking()
    )

    assert report.loaded is True
    assert report.counts["episodes"].added == 1
    assert len((await stored(store)).episodes) == 2


async def test_breaking_stored_entities_rolls_back(
    tmp_path: Path, store: InMemoryKnowledgeStore
) -> None:
    await load_package(write_package(tmp_path / "a", BASE), store, ticking())
    before = await stored(store)
    pin_without_movies = PIN.model_copy(
        update={"versions": (CharacterVersion.model_validate(version("classic")),)}
    )

    report = await load_package(
        write_package(tmp_path / "b", [pin_without_movies]), store, ticking()
    )

    assert report.loaded is False
    assert [(i.file, i.path, i.code) for i in report.issues] == [
        ("db:episodes/film_main", "characters[0]", "continuity_mismatch")
    ]
    assert await stored(store) == before
    async with store.transaction() as transaction:
        assert len(await transaction.read_revisions(entity_ref(PIN))) == 1
        assert await transaction.read_load(2) is None


async def test_reference_missing_everywhere_is_an_error(
    tmp_path: Path, store: InMemoryKnowledgeStore
) -> None:
    episode = Episode.model_validate(
        {"id": "s01e01", "work": "series", "number": 1, "title": "Серия"}
    )

    report = await load_package(write_package(tmp_path, [episode]), store, ticking())

    assert report.loaded is False
    assert [(i.file, i.path, i.code) for i in report.issues] == [
        ("episodes/s01e01.yaml", "work", "unknown_reference")
    ]


class FailingStore(KnowledgeStore):
    def __init__(self, error: Exception) -> None:
        self._error = error

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[KnowledgeTransaction]:
        raise self._error
        yield  # pragma: no cover

    async def snapshot(self):
        raise self._error

    async def revision_history(self, ref):
        raise self._error


@pytest.mark.parametrize(
    ("error", "code"),
    [
        (KnowledgeStoreUnavailableError(), "database_unavailable"),
        (KnowledgeSchemaNotReadyError(), "schema_not_ready"),
        (KnowledgeDataInvalidError(), "stored_data_invalid"),
    ],
)
async def test_store_failures_are_reported(
    tmp_path: Path, error: Exception, code: str
) -> None:
    report = await load_package(
        write_package(tmp_path, [CLASSIC]), FailingStore(error), ticking()
    )

    assert report.loaded is False
    assert [issue.code for issue in report.issues] == [code]
    assert report.issues[0].message


async def test_matching_revision_allows_the_change(
    tmp_path: Path, store: InMemoryKnowledgeStore
) -> None:
    await load_package(write_package(tmp_path / "a", BASE), store, ticking())
    changed = KROSH.model_copy(update={"species": "заяц"})

    report = await load_package(
        write_package(
            tmp_path / "b",
            [changed],
            {"characters": {"krosh": 1}},
        ),
        store,
        ticking(),
    )

    assert report.loaded is True
    assert report.counts["characters"].updated == 1
    assert (
        next(c for c in (await stored(store)).characters if c.id == "krosh") == changed
    )


async def test_revision_conflict_rejects_the_whole_package(
    tmp_path: Path, store: InMemoryKnowledgeStore
) -> None:
    await load_package(write_package(tmp_path / "a", BASE), store, ticking())
    changed = KROSH.model_copy(update={"species": "заяц"})
    await load_package(write_package(tmp_path / "b", [changed]), store, ticking())
    before = await stored(store)

    report = await load_package(
        write_package(
            tmp_path / "c",
            [changed],
            {"characters": {"krosh": 1}},
        ),
        store,
        ticking(),
    )

    assert report.loaded is False
    assert [(issue.file, issue.path, issue.code) for issue in report.issues] == [
        ("characters/krosh.yaml", "revisions", "revision_mismatch")
    ]
    assert "ожидалась ревизия 1, в БД 2" in report.issues[0].message
    assert await stored(store) == before
    async with store.transaction() as transaction:
        assert await transaction.read_load(3) is None


async def test_revision_conflict_for_missing_entity(
    tmp_path: Path, store: InMemoryKnowledgeStore
) -> None:
    await load_package(write_package(tmp_path / "a", BASE), store, ticking())
    krosh = next(c for c in BASE if getattr(c, "id", None) == "krosh")
    async with store.transaction() as transaction:
        load_id = await transaction.start_load(START)
        await transaction.save(
            load_id, [EntityChange(operation="delete", entity=krosh)]
        )
        await transaction.finish_load(
            load_id,
            LoadSummary(finished_at=START, duration_ms=0, entity_count=0, counts={}),
        )

    report = await load_package(
        write_package(
            tmp_path / "b",
            [krosh],
            {"characters": {"krosh": 1}},
        ),
        store,
        ticking(),
    )

    assert report.loaded is False
    assert [(issue.file, issue.code) for issue in report.issues] == [
        ("characters/krosh.yaml", "revision_mismatch")
    ]
    assert "отсутствует" in report.issues[0].message


async def test_multiple_conflicts_are_all_reported(
    tmp_path: Path, store: InMemoryKnowledgeStore
) -> None:
    await load_package(write_package(tmp_path / "a", BASE), store, ticking())
    changed = [
        KROSH.model_copy(update={"species": "заяц"}),
        PIN.model_copy(update={"species": "птица"}),
    ]
    await load_package(write_package(tmp_path / "b", changed), store, ticking())

    report = await load_package(
        write_package(
            tmp_path / "c",
            changed,
            {"characters": {"krosh": 1, "pin": 1}},
        ),
        store,
        ticking(),
    )

    assert report.loaded is False
    assert [issue.file for issue in report.issues] == [
        "characters/krosh.yaml",
        "characters/pin.yaml",
    ]
    assert all(issue.code == "revision_mismatch" for issue in report.issues)


async def test_load_event_has_only_safe_fields(
    tmp_path: Path, store: InMemoryKnowledgeStore, caplog
) -> None:
    await load_package(write_package(tmp_path / "a", BASE), store, ticking())
    caplog.set_level("INFO", logger="smeshariki_ai.rag.services")

    await load_package(write_package(tmp_path / "b", BASE), store, ticking())

    record = next(r for r in caplog.records if r.event == "rag.load.completed")
    assert record.outcome == "loaded"
    assert record.conflict_count == 0
    assert "krosh" not in str(record.log_fields)
