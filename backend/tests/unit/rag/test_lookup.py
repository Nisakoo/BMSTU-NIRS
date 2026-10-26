import logging
from datetime import UTC, datetime

import pytest

from smeshariki_ai.rag.lookup import (
    NOT_FOUND_MESSAGE,
    UNAVAILABLE_MESSAGE,
    KnowledgeLookup,
)
from smeshariki_ai.rag.memory import InMemoryKnowledgeStore
from smeshariki_ai.rag.models import (
    Artifact,
    Character,
    Continuity,
    Episode,
    KnowledgeEntity,
    Location,
    Work,
)
from smeshariki_ai.rag.ports import (
    EntityChange,
    FoundKnowledge,
    KnowledgeDataInvalidError,
    KnowledgeReader,
    KnowledgeSchemaNotReadyError,
    KnowledgeStoreUnavailableError,
    LoadSummary,
)

STARTED = datetime(2026, 10, 26, 12, 0, tzinfo=UTC)
# Synthetic knowledge: every name and fact here is made up for the tests.
PIN = Character.model_validate(
    {
        "id": "pin",
        "name": "Пин",
        "aliases": ["Пин-механик"],
        "species": "пингвин",
        "versions": [
            {
                "continuities": ["classic", "movies"],
                "age_group": "adult",
                "traits": ["изобретательный", "немногословный"],
                "speech_style": {
                    "register": "короткие фразы",
                    "markers": ["акцент"],
                    "constraints": ["не кричит"],
                },
                "catchphrases": ["Гут!"],
                "sources": [{"document": "Справочник"}],
            }
        ],
        "relationships": [
            {"to": "krosh", "type": "friendship", "continuities": ["classic"]}
        ],
    }
)
KROSH = Character.model_validate(
    {
        "id": "krosh",
        "name": "Крош",
        "species": "кролик",
        "versions": [
            {
                "continuities": ["classic"],
                "age_group": "child",
                "traits": ["весёлый"],
                "speech_style": {"register": "разговорный"},
            }
        ],
    }
)
HOUSE = Location.model_validate(
    {
        "id": "pin_house",
        "name": "Дом Пина",
        "description": "Мастерская у моря.",
        "continuities": ["classic"],
        "residents": ["pin"],
    }
)
PLANE = Artifact.model_validate(
    {
        "id": "pin_plane",
        "name": "Самолёт Пина",
        "artifact_type": "машина",
        "description": "Самодельный самолёт.",
        "capabilities": ["летает"],
        "limitations": ["часто ломается"],
        "continuities": ["classic"],
        "creators": ["pin"],
    }
)
EPISODE = Episode.model_validate(
    {
        "id": "s01e01",
        "work": "series",
        "season": 1,
        "number": 1,
        "title": "Пинг-понг",
        "characters": ["pin", "krosh"],
        "locations": ["pin_house"],
        "artifacts": ["pin_plane"],
        "interactions": [
            {
                "from": "krosh",
                "to": "pin",
                "type": "conflict",
                "description": "Спор о ракетке.",
            }
        ],
    }
)
BASE: list[KnowledgeEntity] = [
    Continuity(id="classic", name="Классический сериал"),
    Continuity(id="movies", name="Фильмы"),
    Work.model_validate(
        {"id": "series", "title": "Сериал", "kind": "series", "continuity": "classic"}
    ),
    PIN,
    KROSH,
    HOUSE,
    PLANE,
    EPISODE,
]


async def load(store: InMemoryKnowledgeStore, entities: list[KnowledgeEntity]) -> None:
    async with store.transaction() as transaction:
        load_id = await transaction.start_load(STARTED)
        await transaction.save(
            load_id, [EntityChange(operation="create", entity=e) for e in entities]
        )
        await transaction.finish_load(
            load_id,
            LoadSummary(finished_at=STARTED, duration_ms=0, entity_count=0, counts={}),
        )


@pytest.fixture
async def store() -> InMemoryKnowledgeStore:
    value = InMemoryKnowledgeStore()
    await load(value, BASE)
    return value


def dump(result) -> dict:
    return result.model_dump(mode="json", by_alias=True)


async def test_character_card_shows_names_instead_of_slugs(
    store: InMemoryKnowledgeStore,
) -> None:
    result = await KnowledgeLookup(store).lookup("  пин-МЕХАНИК ")

    assert dump(result) == {
        "status": "found",
        "total": 1,
        "truncated": False,
        "message": None,
        "matches": [
            {
                "type": "character",
                "id": "pin",
                "name": "Пин",
                "aliases": ["Пин-механик"],
                "species": "пингвин",
                "versions": [
                    {
                        "continuities": ["Классический сериал", "Фильмы"],
                        "age_group": "adult",
                        "traits": ["изобретательный", "немногословный"],
                        "speech_style": {
                            "register": "короткие фразы",
                            "markers": ["акцент"],
                            "constraints": ["не кричит"],
                        },
                        "catchphrases": ["Гут!"],
                    }
                ],
                "relationships": [
                    {
                        "to": "Крош",
                        "type": "friendship",
                        "continuities": ["Классический сериал"],
                        "description": None,
                    }
                ],
            }
        ],
    }


async def test_location_and_artifact_cards(store: InMemoryKnowledgeStore) -> None:
    lookup = KnowledgeLookup(store)

    location = dump(await lookup.lookup("дом пина"))["matches"]
    artifact = dump(await lookup.lookup("Самолет Пина"))["matches"]

    assert location == [
        {
            "type": "location",
            "id": "pin_house",
            "name": "Дом Пина",
            "aliases": [],
            "description": "Мастерская у моря.",
            "continuities": ["Классический сериал"],
            "residents": ["Пин"],
        }
    ]
    assert artifact == [
        {
            "type": "artifact",
            "id": "pin_plane",
            "name": "Самолёт Пина",
            "aliases": [],
            "artifact_type": "машина",
            "description": "Самодельный самолёт.",
            "capabilities": ["летает"],
            "limitations": ["часто ломается"],
            "continuities": ["Классический сериал"],
            "creators": ["Пин"],
        }
    ]


async def test_episode_card_by_title(store: InMemoryKnowledgeStore) -> None:
    result = dump(await KnowledgeLookup(store).lookup("пинг-понг"))

    assert result["matches"] == [
        {
            "type": "episode",
            "id": "s01e01",
            "title": "Пинг-понг",
            "work": "Сериал",
            "continuity": "Классический сериал",
            "season": 1,
            "number": 1,
            "characters": ["Пин", "Крош"],
            "locations": ["Дом Пина"],
            "artifacts": ["Самолёт Пина"],
            "interactions": [
                {
                    "from": "Крош",
                    "to": "Пин",
                    "type": "conflict",
                    "description": "Спор о ракетке.",
                }
            ],
        }
    ]


async def test_cards_are_ordered_by_type_then_id(store: InMemoryKnowledgeStore) -> None:
    hill = HOUSE.model_copy(update={"id": "a_hill", "name": "Крош", "residents": ()})
    rocket = PLANE.model_copy(update={"id": "rocket", "name": "Крош"})
    episode = EPISODE.model_copy(update={"id": "s01e02", "number": 2, "title": "Крош"})
    await load(store, [hill, rocket, episode])

    result = await KnowledgeLookup(store).lookup("крош")

    assert [(card.type, card.id) for card in result.matches] == [
        ("character", "krosh"),
        ("location", "a_hill"),
        ("artifact", "rocket"),
        ("episode", "s01e02"),
    ]


async def test_matches_are_limited(store: InMemoryKnowledgeStore) -> None:
    await load(
        store,
        [
            EPISODE.model_copy(
                update={"id": f"e{index:02}", "number": index + 10, "title": "Повтор"}
            )
            for index in range(12)
        ],
    )

    result = await KnowledgeLookup(store).lookup("повтор")
    narrow = await KnowledgeLookup(store, limit=3).lookup("повтор")

    assert (result.status, result.total, result.truncated) == ("found", 12, True)
    assert [card.id for card in result.matches] == [f"e{i:02}" for i in range(10)]
    assert (len(narrow.matches), narrow.truncated) == (3, True)


async def test_unknown_name_is_not_found(store: InMemoryKnowledgeStore) -> None:
    result = await KnowledgeLookup(store).lookup("Бармалей")

    assert dump(result) == {
        "status": "not_found",
        "total": 0,
        "truncated": False,
        "matches": [],
        "message": NOT_FOUND_MESSAGE,
    }


async def test_empty_store_is_unavailable(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger="smeshariki_ai.rag.lookup")

    result = await KnowledgeLookup(InMemoryKnowledgeStore()).lookup("Пин")

    assert (result.status, result.message) == ("unavailable", UNAVAILABLE_MESSAGE)
    assert caplog.records[0].reason == "not_loaded"


class FailingReader(KnowledgeReader):
    def __init__(self, error: Exception) -> None:
        self.error = error

    async def find(self, key: str) -> FoundKnowledge:
        raise self.error

    async def has_knowledge(self) -> bool:
        raise self.error


@pytest.mark.parametrize(
    "error",
    [
        KnowledgeStoreUnavailableError(),
        KnowledgeSchemaNotReadyError(),
        KnowledgeDataInvalidError(),
    ],
)
async def test_store_errors_mean_unavailable(
    error: Exception, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO, logger="smeshariki_ai.rag.lookup")

    result = await KnowledgeLookup(FailingReader(error)).lookup("Пин")

    assert result.status == "unavailable"
    [record] = caplog.records
    assert record.levelno == logging.WARNING
    assert record.error_type == type(error).__name__


async def test_other_errors_are_not_hidden() -> None:
    with pytest.raises(RuntimeError):
        await KnowledgeLookup(FailingReader(RuntimeError())).lookup("Пин")


async def test_log_event_has_no_query_or_knowledge(
    store: InMemoryKnowledgeStore, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO, logger="smeshariki_ai.rag.lookup")

    await KnowledgeLookup(store).lookup("Пин-механик")

    [record] = caplog.records
    assert record.event == "rag.lookup.completed"
    assert (record.outcome, record.match_count) == ("found", 1)
    assert record.started_at and record.duration_ms >= 0
    logged = caplog.text + repr(vars(record))
    for secret in ("Пин", "механик", "пингвин", "Гут"):
        assert secret not in logged
