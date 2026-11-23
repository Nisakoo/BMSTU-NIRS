from __future__ import annotations

from test_lookup import KROSH

from smeshariki_ai.agent.models import ToolCall
from smeshariki_ai.agent.tools import ToolRegistry
from smeshariki_ai.rag.memory import InMemoryKnowledgeStore
from smeshariki_ai.rag.models import KnowledgeSet
from smeshariki_ai.rag.ports import (
    FoundKnowledge,
    KnowledgeReader,
    KnowledgeStoreUnavailableError,
)
from smeshariki_ai.rag.story_canon import StoryCanonLookup
from smeshariki_ai.rag.tools import GetStoryCanonTool


class FailingReader(KnowledgeReader):
    async def find(self, key: str) -> FoundKnowledge:
        raise KnowledgeStoreUnavailableError

    async def suggest(self, key: str, limit: int = 5):
        return ()

    async def has_knowledge(self) -> bool:
        return False


def registry(reader: KnowledgeReader) -> ToolRegistry:
    return ToolRegistry((GetStoryCanonTool(StoryCanonLookup(reader)),))


def call(arguments: dict) -> ToolCall:
    return ToolCall(id="call-1", name="get_story_canon", arguments=arguments)


def test_definition_describes_a_compact_profile() -> None:
    [definition] = registry(InMemoryKnowledgeStore()).definitions

    assert definition.name == "get_story_canon"
    for phrase in (
        "at most once per story",
        "age group",
        "relationships",
        "never returns free-text descriptions",
        "not as a plot",
        "lookup_knowledge",
        "search_lore",
    ):
        assert phrase in definition.description
    assert definition.parameters["required"] == ["names"]
    assert definition.parameters["properties"]["names"]["minItems"] == 1
    assert definition.parameters["properties"]["names"]["maxItems"] == 3


async def test_empty_store_returns_safe_unavailable() -> None:
    result = await registry(InMemoryKnowledgeStore()).execute(
        call({"names": ["Бармалей"]})
    )

    assert result.error is None
    assert result.output["status"] == "unavailable"
    assert result.output["characters"] == []


async def test_failing_reader_returns_safe_unavailable() -> None:
    result = await registry(FailingReader()).execute(call({"names": ["Крош"]}))

    assert result.error is None
    assert result.output["status"] == "unavailable"
    assert result.output["characters"] == []


async def test_invalid_arguments_do_not_execute_the_reader() -> None:
    registry_ = registry(FailingReader())

    empty = await registry_.execute(call({"names": []}))
    too_many = await registry_.execute(call({"names": ["Крош", "Пин", "Ёжик", "Нюша"]}))
    extra = await registry_.execute(call({"names": ["Крош"], "description": "нельзя"}))

    for result in (empty, too_many, extra):
        assert result.error is not None
        assert result.error.code == "invalid_arguments"


def test_arguments_model_has_no_extra_fields() -> None:
    model = GetStoryCanonTool.arguments_model
    schema = model.model_json_schema()

    assert schema["additionalProperties"] is False
    assert schema["required"] == ["names"]


async def test_registry_can_load_a_found_profile() -> None:
    class Reader(KnowledgeReader):
        async def find(self, key: str) -> FoundKnowledge:
            return FoundKnowledge(
                entities=KnowledgeSet(characters=(KROSH,)),
                names={},
            )

        async def suggest(self, key: str, limit: int = 5):
            return ()

        async def has_knowledge(self) -> bool:
            return True

    result = await registry(Reader()).execute(call({"names": ["Крош"]}))

    assert result.error is None
    assert result.output["status"] == "found"
    assert result.output["characters"][0]["name"] == "Крош"
