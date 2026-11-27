from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from smeshariki_ai.rag.lore.chunking import ChunkingConfig, chunk_text
from smeshariki_ai.rag.lore.embeddings import EmbeddingProvider, cosine
from smeshariki_ai.rag.lore.models import LoreDocument, LoreHit


class DenseSearcher(Protocol):
    """Returns dense candidates as hits; only ``document_id`` and ``score`` matter."""

    async def search(self, text: str, limit: int) -> tuple[LoreHit, ...]: ...


class InMemoryDenseIndex:
    """Exact cosine search over the chunks of one lore package.

    It is the offline counterpart of the pgvector index: the same hits and the
    same fusion, but without PostgreSQL. It keeps the retrieval code testable
    before the vectors land in the database.
    """

    def __init__(
        self,
        *,
        provider: EmbeddingProvider,
        hits: tuple[LoreHit, ...],
        vectors: tuple[tuple[float, ...], ...],
    ) -> None:
        if len(hits) != len(vectors):
            raise ValueError("hits and vectors must have the same length")
        self._provider = provider
        self._hits = hits
        self._vectors = vectors

    @classmethod
    async def build(
        cls,
        provider: EmbeddingProvider,
        documents: Sequence[LoreDocument],
        *,
        chunking: ChunkingConfig | None = None,
    ) -> InMemoryDenseIndex:
        texts: list[str] = []
        hits: list[LoreHit] = []
        for document in documents:
            for position, text in enumerate(chunk_text(document.text, chunking)):
                hits.append(
                    LoreHit(
                        document_id=document.id,
                        position=position,
                        title=document.title,
                        source=document.source,
                        text=text,
                        score=0.0,
                        rank=1,
                    )
                )
                texts.append(text)
        vectors = await provider.embed(texts)
        return cls(provider=provider, hits=tuple(hits), vectors=vectors)

    async def search(self, text: str, limit: int) -> tuple[LoreHit, ...]:
        if limit <= 0 or not self._hits:
            return ()
        query = await self._provider.embed_query(text)
        scored = [
            LoreHit(
                chunk_id=hit.chunk_id,
                document_id=hit.document_id,
                position=hit.position,
                title=hit.title,
                source=hit.source,
                text=hit.text,
                score=cosine(query, vector),
                rank=1,
            )
            for hit, vector in zip(self._hits, self._vectors, strict=True)
        ]
        scored.sort(key=lambda hit: hit.score, reverse=True)
        return tuple(
            hit.model_copy(update={"rank": rank})
            for rank, hit in enumerate(scored[:limit], start=1)
        )


def fuse_hits(
    bm25_hits: Sequence[LoreHit],
    dense_hits: Sequence[LoreHit],
    *,
    weight: float,
) -> tuple[LoreHit, ...]:
    """Merge two candidate lists into one document-level ranking.

    ``weight`` is the share of BM25: ``1.0`` reproduces the lexical order and
    ``0.0`` the dense one. Scores keep the BM25 scale so the context builder's
    absolute ``min_score`` filter keeps working: the fused document score is
    scaled by the best BM25 score of the query.
    """

    if not 0.0 <= weight <= 1.0:
        raise ValueError("weight must be between 0 and 1")
    bm25_best = _best_scores(bm25_hits)
    dense_best = _best_scores(dense_hits)
    if not bm25_best and not dense_best:
        return ()
    bm25_norm = _normalize(bm25_best)
    dense_norm = _normalize({doc: max(0.0, score) for doc, score in dense_best.items()})
    scale = max(bm25_best.values(), default=1.0)

    documents = list(dict.fromkeys([*bm25_best, *dense_best]))
    fused = {
        document: weight * bm25_norm.get(document, 0.0)
        + (1.0 - weight) * dense_norm.get(document, 0.0)
        for document in documents
    }
    bm25_rank = _ranks(bm25_hits)
    dense_rank = _ranks(dense_hits)
    ranked = sorted(
        documents,
        key=lambda document: (
            -fused[document],
            bm25_rank.get(document, len(bm25_rank) + 1),
            dense_rank.get(document, len(dense_rank) + 1),
        ),
    )

    bm25_hit = _best_hit(bm25_hits)
    dense_hit = _best_hit(dense_hits)
    return tuple(
        (bm25_hit.get(document) or dense_hit[document]).model_copy(
            update={"score": fused[document] * scale, "rank": rank}
        )
        for rank, document in enumerate(ranked, start=1)
    )


def _best_scores(hits: Sequence[LoreHit]) -> dict[str, float]:
    best: dict[str, float] = {}
    for hit in hits:
        if hit.score > best.get(hit.document_id, float("-inf")):
            best[hit.document_id] = hit.score
    return best


def _best_hit(hits: Sequence[LoreHit]) -> dict[str, LoreHit]:
    best: dict[str, LoreHit] = {}
    for hit in hits:
        current = best.get(hit.document_id)
        if current is None or hit.score > current.score:
            best[hit.document_id] = hit
    return best


def _ranks(hits: Sequence[LoreHit]) -> dict[str, int]:
    ranks: dict[str, int] = {}
    for hit in hits:
        ranks.setdefault(hit.document_id, hit.rank)
    return ranks


def _normalize(scores: dict[str, float]) -> dict[str, float]:
    if not scores:
        return {}
    highest = max(scores.values())
    if highest <= 0:
        return {document: 0.0 for document in scores}
    return {document: score / highest for document, score in scores.items()}
