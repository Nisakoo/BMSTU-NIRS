"""In-memory BM25 index for tests and benchmarks, never for production."""

from __future__ import annotations

import asyncio
from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence

from smeshariki_ai.rag.lore.bm25 import Bm25Params, rank, score
from smeshariki_ai.rag.lore.models import (
    LoreChunk,
    LoreDocument,
    LoreEntry,
    LoreHit,
    LoreLoadSummary,
)
from smeshariki_ai.rag.lore.ports import (
    LoreDocumentSource,
    LoreIndex,
    LoreStore,
)


class InMemoryBm25Index(LoreStore, LoreIndex, LoreDocumentSource):
    """A deterministic index used by unit tests and the benchmark."""

    def __init__(self) -> None:
        self._documents: dict[str, LoreDocument] = {}
        self._chunks: dict[int, LoreChunk] = {}
        self._postings: dict[str, dict[int, int]] = {}
        self._lengths: dict[int, int] = {}
        self._order: dict[int, tuple[str, int]] = {}
        self._tags: dict[str, frozenset[str]] = {}
        self._version = 0
        self._lock = asyncio.Lock()

    async def replace(self, entries: Iterable[LoreEntry]) -> LoreLoadSummary:
        async with self._lock:
            documents: dict[str, LoreDocument] = {}
            chunks: dict[int, LoreChunk] = {}
            postings: dict[str, dict[int, int]] = defaultdict(dict)
            lengths: dict[int, int] = {}
            order: dict[int, tuple[str, int]] = {}
            tags: dict[str, frozenset[str]] = {}
            next_id = 1
            for entry in entries:
                documents[entry.document.id] = entry.document
                tags[entry.document.id] = frozenset(entry.document.tags)
                for chunk in entry.chunks:
                    chunk_id = next_id
                    next_id += 1
                    chunks[chunk_id] = chunk
                    lengths[chunk_id] = chunk.term_count
                    order[chunk_id] = (chunk.document_id, chunk.position)
                    for term, frequency in Counter(chunk.terms).items():
                        postings[term][chunk_id] = frequency
            self._documents = documents
            self._chunks = chunks
            self._postings = dict(postings)
            self._lengths = lengths
            self._order = order
            self._tags = tags
            self._version += 1
            return LoreLoadSummary(
                version=self._version,
                document_count=len(documents),
                chunk_count=len(chunks),
                term_count=len(postings),
            )

    async def search(
        self,
        terms: Sequence[str],
        top_k: int,
        params: Bm25Params,
        tags: Sequence[str] = (),
    ) -> tuple[LoreHit, ...]:
        async with self._lock:
            if not self._chunks:
                return ()
            average_length = (
                sum(self._lengths.values()) / len(self._lengths)
                if self._lengths
                else 0.0
            )
            scores = score(
                terms,
                self._postings,
                self._lengths,
                len(self._chunks),
                average_length,
                params,
            )
            if tags:
                wanted = set(tags)
                scores = {
                    chunk_id: value
                    for chunk_id, value in scores.items()
                    if self._tags.get(self._chunks[chunk_id].document_id, frozenset())
                    & wanted
                }
            ranked = rank(scores, self._order, top_k)
            return tuple(
                self._hit(chunk_id, position, scores[chunk_id])
                for position, chunk_id in enumerate(ranked, start=1)
            )

    async def version(self) -> int:
        async with self._lock:
            return self._version

    async def documents(self) -> tuple[LoreDocument, ...]:
        async with self._lock:
            return tuple(self._documents[item] for item in sorted(self._documents))

    def _hit(self, chunk_id: int, position: int, value: float) -> LoreHit:
        chunk = self._chunks[chunk_id]
        document = self._documents[chunk.document_id]
        return LoreHit(
            chunk_id=chunk_id,
            document_id=document.id,
            position=chunk.position,
            title=document.title,
            source=document.source,
            text=chunk.text,
            score=value,
            rank=position,
        )
