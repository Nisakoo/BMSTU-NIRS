import pytest
from test_lookup import BASE, load

from smeshariki_ai.agent.models import ToolCall
from smeshariki_ai.agent.tools import ToolRegistry
from smeshariki_ai.rag.lookup import (
    NOT_FOUND_MESSAGE,
    UNAVAILABLE_MESSAGE,
    KnowledgeLookup,
)
from smeshariki_ai.rag.memory import InMemoryKnowledgeStore
from smeshariki_ai.rag.ports import FoundKnowledge, KnowledgeReader
from smeshariki_ai.rag.tools import LookupKnowledgeTool


class CountingReader(KnowledgeReader):
    def __init__(self, store: InMemoryKnowledgeStore) -> None:
        self.store = store
        self.calls = 0

    async def find(self, key: str) -> FoundKnowledge:
        self.calls += 1
        return await self.store.find(key)

    async def has_knowledge(self) -> bool:
        return await self.store.has_knowledge()


@pytest.fixture
async def reader() -> CountingReader:
    store = InMemoryKnowledgeStore()
    await load(store, BASE)
    return CountingReader(store)


def registry(reader: KnowledgeReader) -> ToolRegistry:
    return ToolRegistry((LookupKnowledgeTool(KnowledgeLookup(reader)),))


def call(arguments: dict) -> ToolCall:
    return ToolCall(id="call-1", name="lookup_knowledge", arguments=arguments)


def test_definition_describes_when_to_call_and_the_arguments(
    reader: CountingReader,
) -> None:
    [definition] = registry(reader).definitions

    assert definition.name == "lookup_knowledge"
    for phrase in ("character", "episode", "nickname", "not_found", "invented"):
        assert phrase in definition.description
    assert definition.parameters["required"] == ["name"]
    assert definition.parameters["additionalProperties"] is False
    assert definition.parameters["properties"]["name"]["maxLength"] == 200


async def test_found_card_is_returned_as_json(reader: CountingReader) -> None:
    result = await registry(reader).execute(call({"name": "Пинг-понг"}))

    assert result.error is None
    assert result.output["status"] == "found"
    [card] = result.output["matches"]
    assert card["type"] == "episode"
    assert card["interactions"][0]["from"] == "Крош"


async def test_not_found_and_unavailable_explain_themselves(
    reader: CountingReader,
) -> None:
    missing = await registry(reader).execute(call({"name": "Бармалей"}))
    empty = await registry(CountingReader(InMemoryKnowledgeStore())).execute(
        call({"name": "Пин"})
    )

    assert missing.output["message"] == NOT_FOUND_MESSAGE
    assert (empty.output["status"], empty.output["message"]) == (
        "unavailable",
        UNAVAILABLE_MESSAGE,
    )


@pytest.mark.parametrize(
    "arguments",
    [{}, {"name": "   "}, {"name": "п" * 201}, {"name": "Пин", "type": "character"}],
)
async def test_invalid_arguments_do_not_reach_the_store(
    reader: CountingReader, arguments: dict
) -> None:
    result = await registry(reader).execute(call(arguments))

    assert result.error is not None and result.error.code == "invalid_arguments"
    assert reader.calls == 0
