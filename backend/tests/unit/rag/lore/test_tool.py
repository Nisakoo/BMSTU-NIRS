from __future__ import annotations

import logging
from collections.abc import Sequence

from smeshariki_ai.agent.models import ToolCall
from smeshariki_ai.agent.tools import ToolRegistry
from smeshariki_ai.rag.lore.analyzer import SimpleAnalyzer
from smeshariki_ai.rag.lore.bm25 import Bm25Params
from smeshariki_ai.rag.lore.context import LoreContextBuilder
from smeshariki_ai.rag.lore.index import InMemoryBm25Index
from smeshariki_ai.rag.lore.models import (
    LoreChunk,
    LoreDocument,
    LoreEntry,
    LoreHit,
)
from smeshariki_ai.rag.lore.ports import (
    LoreIndex,
    LoreStoreUnavailableError,
)
from smeshariki_ai.rag.lore.services import SearchLore
from smeshariki_ai.rag.lore.tools import SearchLoreTool

ANALYZER = SimpleAnalyzer()


def entry(document_id: str, title: str, text: str) -> LoreEntry:
    document = LoreDocument(id=document_id, title=title, text=text)
    return LoreEntry(
        document=document,
        chunks=(
            LoreChunk(
                document_id=document_id,
                position=0,
                text=text,
                terms=ANALYZER.terms(text),
            ),
        ),
    )


def registry(index: LoreIndex) -> ToolRegistry:
    return ToolRegistry(
        (
            SearchLoreTool(
                SearchLore(index, ANALYZER),
                LoreContextBuilder(),
            ),
        )
    )


def call(arguments: dict) -> ToolCall:
    return ToolCall(id="call-1", name="search_lore", arguments=arguments)


class FailingIndex(LoreIndex):
    async def search(
        self, terms: Sequence[str], top_k: int, params: Bm25Params
    ) -> tuple[LoreHit, ...]:
        raise LoreStoreUnavailableError

    async def version(self) -> int:
        return 0


def test_definition_describes_a_bounded_reference_tool() -> None:
    [definition] = registry(InMemoryBm25Index()).definitions

    assert definition.name == "search_lore"
    for phrase in (
        "at most once per story",
        "reference material",
        "not as a plot to copy",
        "do not enumerate",
        "empty or unavailable",
    ):
        assert phrase in definition.description
    assert definition.parameters["required"] == ["query"]
    assert definition.parameters["additionalProperties"] is False
    assert definition.parameters["properties"]["query"]["maxLength"] == 300


async def test_found_passages_are_compact_json() -> None:
    index = InMemoryBm25Index()
    await index.replace(
        (
            entry("a", "Полянка", "Крош и Ёжик поссорились из-за игры."),
            entry("b", "Космос", "Пин построил ракету для друзей."),
        )
    )

    result = await registry(index).execute(call({"query": "Крош Ёжик поссорились"}))

    assert result.error is None
    assert result.output["status"] == "found"
    [passage] = result.output["passages"]
    assert passage["title"] == "Полянка"
    assert passage["source"] is None
    assert "Крош" in passage["text"]
    assert set(passage) == {"title", "source", "text"}
    assert "score" not in result.output
    assert "document_id" not in passage
    assert "chunk_id" not in passage
    assert "position" not in passage


async def test_empty_index_returns_safe_status() -> None:
    result = await registry(InMemoryBm25Index()).execute(call({"query": "Крош"}))

    assert result.error is None
    assert result.output["status"] == "empty"
    assert result.output["passages"] == []
    assert "Продолжай" in result.output["message"]


async def test_unavailable_index_returns_safe_status() -> None:
    result = await registry(FailingIndex()).execute(call({"query": "Крош"}))

    assert result.error is None
    assert result.output["status"] == "unavailable"
    assert result.output["passages"] == []
    assert "недоступна" in result.output["message"]


async def test_name_only_query_returns_no_context() -> None:
    index = InMemoryBm25Index()
    await index.replace((entry("a", "Полянка", "Крош и Ёжик поссорились из-за игры."),))

    result = await registry(index).execute(call({"query": "Крош и Ёжик"}))

    assert result.error is None
    assert result.output["status"] == "empty"
    assert result.output["passages"] == []


async def test_events_show_retrieval_and_context_without_text(caplog) -> None:
    index = InMemoryBm25Index()
    await index.replace((entry("a", "Полянка", "Крош и Ёжик построили качели."),))
    registry_ = ToolRegistry(
        (
            SearchLoreTool(
                SearchLore(index, ANALYZER),
                LoreContextBuilder(min_score=0.5),
            ),
        )
    )
    caplog.set_level(logging.INFO)

    await registry_.execute(call({"query": "Крош Ёжик качели"}))

    assert "lore.tool.completed" in caplog.text
    assert "passage_count=1" in caplog.text
    assert "context_chars=" in caplog.text
    assert "quality" not in caplog.text
    assert "Полянка" not in caplog.text


async def test_invalid_arguments_do_not_execute_the_index() -> None:
    registry_ = registry(InMemoryBm25Index())

    empty = await registry_.execute(call({"query": ""}))
    extra = await registry_.execute(call({"query": "Крош", "top_k": 100}))

    assert empty.error is not None
    assert empty.error.code == "invalid_arguments"
    assert extra.error is not None
    assert extra.error.code == "invalid_arguments"


def test_tool_accepts_only_its_argument_model() -> None:
    tool = SearchLoreTool(SearchLore(InMemoryBm25Index(), ANALYZER))

    assert tool.name == "search_lore"
    schema = tool.arguments_model.model_json_schema()
    assert schema["required"] == ["query"]
    assert schema["additionalProperties"] is False
