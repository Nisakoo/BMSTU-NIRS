"""PostgreSQL adapters of the BM25 lore search.

PostgreSQL stores the corpus and the derived inverted index. Scoring is a
single set-based SQL query over postings, so the backend never loads the whole
corpus into memory and the number of queries does not grow with the corpus.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Iterable, Iterator, Sequence
from contextlib import contextmanager
from datetime import UTC, datetime
from itertools import islice
from typing import Any

from asyncpg import PostgresError
from pydantic import ValidationError
from sqlalchemy import (
    ARRAY,
    Text,
    bindparam,
    delete,
    func,
    insert,
    select,
    text,
    update,
)
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from smeshariki_ai.rag.lore import tables
from smeshariki_ai.rag.lore.bm25 import Bm25Params
from smeshariki_ai.rag.lore.models import (
    LoreDocument,
    LoreEntry,
    LoreHit,
    LoreLoadSummary,
)
from smeshariki_ai.rag.lore.ports import (
    LoreDataInvalidError,
    LoreDocumentSource,
    LoreIndex,
    LoreSchemaNotReadyError,
    LoreStore,
    LoreStoreUnavailableError,
)

_LORE_LOCK_KEY = int.from_bytes(b"rag_lore", "big")
_UNDEFINED_TABLE = "42P01"
_DOCUMENT_BATCH = 50
_POSTING_BATCH = 5000


@contextmanager
def _translate_errors() -> Iterator[None]:
    try:
        yield
    except SQLAlchemyError as error:
        if getattr(getattr(error, "orig", None), "sqlstate", None) == _UNDEFINED_TABLE:
            raise LoreSchemaNotReadyError from error
        raise LoreStoreUnavailableError from error
    except (PostgresError, OSError, TimeoutError) as error:
        raise LoreStoreUnavailableError from error


class PostgresLoreStore(LoreStore):
    """Atomically replaces the lore corpus and its derived index."""

    def __init__(
        self,
        engine: AsyncEngine,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._engine = engine
        self._clock = clock or (lambda: datetime.now(UTC))

    async def replace(self, entries: Iterable[LoreEntry]) -> LoreLoadSummary:
        started_at = self._clock()
        document_count = chunk_count = 0
        with _translate_errors():
            async with self._engine.begin() as connection:
                await connection.execute(
                    text("SELECT pg_advisory_xact_lock(:key)"),
                    {"key": _LORE_LOCK_KEY},
                )
                load_id = await connection.scalar(
                    insert(tables.loads)
                    .values(started_at=started_at)
                    .returning(tables.loads.c.id)
                )
                await _clear(connection)

                source = iter(entries)
                while batch := list(islice(source, _DOCUMENT_BATCH)):
                    docs = [entry.document for entry in batch]
                    chunk_rows: list[dict[str, Any]] = []
                    chunk_terms: list[tuple[str, ...]] = []
                    for entry in batch:
                        for chunk in entry.chunks:
                            chunk_rows.append(
                                {
                                    "document_id": chunk.document_id,
                                    "position": chunk.position,
                                    "text": chunk.text,
                                    "term_count": chunk.term_count,
                                }
                            )
                            chunk_terms.append(chunk.terms)
                    document_count += len(docs)
                    chunk_count += len(chunk_rows)
                    await _insert_documents(connection, docs)
                    if chunk_rows:
                        await connection.execute(insert(tables.chunks), chunk_rows)
                        await _insert_postings(
                            connection,
                            [entry.document.id for entry in batch],
                            chunk_rows,
                            chunk_terms,
                        )

                await connection.execute(
                    text(
                        "INSERT INTO rag_lore_terms (term, df) "
                        "SELECT term, count(*) FROM rag_lore_postings "
                        "GROUP BY term"
                    )
                )
                await connection.execute(
                    text(
                        "INSERT INTO rag_lore_stats (id, n_chunks, avgdl, version) "
                        "SELECT 1, count(*), coalesce(avg(term_count), 0), :version "
                        "FROM rag_lore_chunks"
                    ).bindparams(version=load_id)
                )
                term_count = await connection.scalar(
                    select(func.count()).select_from(tables.terms)
                )
                term_count = int(term_count or 0)
                await connection.execute(
                    update(tables.loads)
                    .where(tables.loads.c.id == load_id)
                    .values(
                        finished_at=self._clock(),
                        document_count=document_count,
                        chunk_count=chunk_count,
                        term_count=term_count,
                    )
                )
        return LoreLoadSummary(
            version=load_id,
            document_count=document_count,
            chunk_count=chunk_count,
            term_count=term_count,
        )


class PostgresLoreDocumentStore(LoreDocumentSource):
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def documents(self) -> tuple[LoreDocument, ...]:
        statement = select(tables.documents).order_by(tables.documents.c.id)
        with _translate_errors():
            async with self._engine.connect() as connection:
                rows = (await connection.execute(statement)).mappings().all()
        try:
            return tuple(_document(row) for row in rows)
        except (ValidationError, ValueError) as error:
            raise LoreDataInvalidError from error

    async def version(self) -> int:
        with _translate_errors():
            async with self._engine.connect() as connection:
                value = await connection.scalar(
                    select(tables.stats.c.version).where(tables.stats.c.id == 1)
                )
        return 0 if value is None else int(value)


class PostgresBm25Index(LoreIndex):
    """Scores postings in PostgreSQL with the BM25 formula from the domain."""

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def search(
        self,
        terms: Sequence[str],
        top_k: int,
        params: Bm25Params,
    ) -> tuple[LoreHit, ...]:
        unique = tuple(dict.fromkeys(term for term in terms if term))
        if not unique or top_k <= 0:
            return ()
        statement = _search_statement()
        with _translate_errors():
            async with self._engine.connect() as connection:
                rows = (
                    await connection.execute(
                        statement,
                        {
                            "terms": list(unique),
                            "top_k": top_k,
                            "k1": params.k1,
                            "b": params.b,
                        },
                    )
                ).mappings()
                return tuple(
                    LoreHit(
                        chunk_id=row["chunk_id"],
                        document_id=row["document_id"],
                        position=row["position"],
                        title=row["title"],
                        source=row["source"],
                        text=row["text"],
                        score=float(row["score"]),
                        rank=position,
                    )
                    for position, row in enumerate(rows, start=1)
                )

    async def version(self) -> int:
        with _translate_errors():
            async with self._engine.connect() as connection:
                value = await connection.scalar(
                    select(tables.stats.c.version).where(tables.stats.c.id == 1)
                )
        return 0 if value is None else int(value)


async def _clear(connection: AsyncConnection) -> None:
    # Child rows go first; the load journal is intentionally kept.
    await connection.execute(delete(tables.postings))
    await connection.execute(delete(tables.terms))
    await connection.execute(delete(tables.chunks))
    await connection.execute(delete(tables.documents))
    await connection.execute(delete(tables.stats))


async def _insert_documents(
    connection: AsyncConnection, documents: Sequence[LoreDocument]
) -> None:
    await connection.execute(
        insert(tables.documents),
        [
            {
                "id": document.id,
                "title": document.title,
                "text": document.text,
                "source": document.source,
                "continuity": document.continuity,
                "characters": list(document.characters),
                "tags": list(document.tags),
            }
            for document in documents
        ],
    )


async def _insert_postings(
    connection: AsyncConnection,
    document_ids: Sequence[str],
    chunk_rows: Sequence[dict[str, Any]],
    chunk_terms: Sequence[tuple[str, ...]],
) -> None:
    rows = await connection.execute(
        select(
            tables.chunks.c.id,
            tables.chunks.c.document_id,
            tables.chunks.c.position,
        )
        .where(tables.chunks.c.document_id.in_(document_ids))
        .order_by(tables.chunks.c.document_id, tables.chunks.c.position)
    )
    ids = {(row.document_id, row.position): row.id for row in rows}
    postings: list[dict[str, Any]] = []
    for row, terms in zip(chunk_rows, chunk_terms, strict=True):
        chunk_id = ids[(row["document_id"], row["position"])]
        for term, frequency in Counter(terms).items():
            postings.append({"term": term, "chunk_id": chunk_id, "tf": frequency})
    for start in range(0, len(postings), _POSTING_BATCH):
        await connection.execute(
            insert(tables.postings), postings[start : start + _POSTING_BATCH]
        )


def _document(row: Any) -> LoreDocument:
    return LoreDocument(
        id=row["id"],
        title=row["title"],
        text=row["text"],
        source=row["source"],
        continuity=row["continuity"],
        characters=tuple(row["characters"] or ()),
        tags=tuple(row["tags"] or ()),
    )


def _search_statement() -> Any:
    return text(
        """
        WITH q(term) AS (
            SELECT unnest(CAST(:terms AS text[]))
        ),
        s AS (
            SELECT n_chunks::double precision AS n_chunks,
                   avgdl
            FROM rag_lore_stats
            WHERE id = 1
        ),
        scored AS (
            SELECT p.chunk_id,
                   SUM(
                       ln(
                           1.0 + (
                               s.n_chunks - t.df::double precision + 0.5
                           ) / (t.df::double precision + 0.5)
                       ) * (
                           p.tf * (CAST(:k1 AS double precision) + 1.0)
                       ) / (
                           p.tf + CAST(:k1 AS double precision) * (
                               1.0 - CAST(:b AS double precision)
                               + CAST(:b AS double precision)
                               * c.term_count::double precision / s.avgdl
                           )
                       )
                   ) AS score
            FROM q
            JOIN rag_lore_terms t ON t.term = q.term
            JOIN rag_lore_postings p ON p.term = q.term
            JOIN rag_lore_chunks c ON c.id = p.chunk_id
            CROSS JOIN s
            WHERE s.n_chunks > 0 AND s.avgdl > 0
            GROUP BY p.chunk_id
        )
        SELECT c.id AS chunk_id,
               c.document_id,
               c.position,
               c.text,
               d.title,
               d.source,
               sc.score
        FROM scored sc
        JOIN rag_lore_chunks c ON c.id = sc.chunk_id
        JOIN rag_lore_documents d ON d.id = c.document_id
        WHERE sc.score > 0
        ORDER BY sc.score DESC, c.document_id, c.position
        LIMIT :top_k
        """
    ).bindparams(
        bindparam("terms", type_=ARRAY(Text)),
        bindparam("top_k"),
        bindparam("k1"),
        bindparam("b"),
    )
