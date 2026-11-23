from __future__ import annotations

from smeshariki_ai.rag.lore.analyzer import SimpleAnalyzer
from smeshariki_ai.rag.lore.bm25 import Bm25Params
from smeshariki_ai.rag.lore.index import InMemoryBm25Index
from smeshariki_ai.rag.lore.models import (
    LoreChunk,
    LoreDocument,
    LoreEntry,
)

ANALYZER = SimpleAnalyzer()
PARAMS = Bm25Params()


def entry(
    document_id: str, title: str, text: str, tags: tuple[str, ...] = ()
) -> LoreEntry:
    document = LoreDocument(id=document_id, title=title, text=text, tags=tags)
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


async def test_index_returns_the_best_matching_chunk() -> None:
    index = InMemoryBm25Index()
    await index.replace(
        (
            entry("a", "A", "Возврат оплаты на карту."),
            entry("b", "B", "Статус оплаты в приложении."),
            entry("c", "C", "Возврат билета через кассу."),
        )
    )

    hits = await index.search(["возврат", "оплаты"], 2, PARAMS)

    assert [hit.document_id for hit in hits] == ["a", "b"]
    assert hits[0].score > hits[1].score
    assert hits[0].rank == 1
    assert hits[0].title == "A"


async def test_tags_filter_the_corpus_before_ranking() -> None:
    index = InMemoryBm25Index()
    await index.replace(
        (
            entry("a", "A", "Крош и Ёжик говорят о дружбе.", ("style",)),
            entry("b", "B", "Крош и Ёжик говорят о дружбе.", ("plot",)),
            entry("c", "C", "Крош и Ёжик говорят о дружбе."),
        )
    )

    style = await index.search(["крош", "ежик"], 5, PARAMS, tags=("style",))
    plot = await index.search(["крош", "ежик"], 5, PARAMS, tags=("plot",))
    any_tag = await index.search(["крош", "ежик"], 5, PARAMS)

    assert [hit.document_id for hit in style] == ["a"]
    assert [hit.document_id for hit in plot] == ["b"]
    assert [hit.document_id for hit in any_tag] == ["a", "b", "c"]


async def test_equal_scores_are_ordered_by_document_and_position() -> None:
    index = InMemoryBm25Index()
    await index.replace(
        (
            entry("b", "B", "Одинаковый текст."),
            entry("a", "A", "Одинаковый текст."),
        )
    )

    hits = await index.search(["одинаковый"], 5, PARAMS)

    assert [hit.document_id for hit in hits] == ["a", "b"]


async def test_empty_index_returns_nothing() -> None:
    index = InMemoryBm25Index()
    assert await index.search(["слово"], 5, PARAMS) == ()
    assert await index.version() == 0


async def test_replace_increments_version_and_replaces_documents() -> None:
    index = InMemoryBm25Index()
    await index.replace((entry("a", "A", "Первый текст."),))
    await index.replace((entry("b", "B", "Второй текст."),))

    assert await index.version() == 2
    assert [document.id for document in await index.documents()] == ["b"]
    assert await index.search(["первый"], 5, PARAMS) == ()
    assert [hit.document_id for hit in await index.search(["второй"], 5, PARAMS)] == [
        "b"
    ]


async def test_query_terms_are_deduplicated() -> None:
    index = InMemoryBm25Index()
    await index.replace((entry("a", "A", "Возврат оплаты."),))

    once = await index.search(["возврат"], 5, PARAMS)
    twice = await index.search(["возврат", "возврат"], 5, PARAMS)

    assert len(once) == len(twice) == 1
    assert once[0].score == twice[0].score
