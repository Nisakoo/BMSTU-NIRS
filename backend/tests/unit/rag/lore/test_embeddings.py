from __future__ import annotations

from pathlib import Path

import pytest

from smeshariki_ai.rag.lore.analyzer import SimpleAnalyzer
from smeshariki_ai.rag.lore.embeddings import (
    EmbeddingUnavailableError,
    FakeEmbeddingProvider,
    LocalEmbeddingProvider,
    cosine,
)
from smeshariki_ai.rag.lore.hybrid import InMemoryDenseIndex, fuse_hits
from smeshariki_ai.rag.lore.index import InMemoryBm25Index
from smeshariki_ai.rag.lore.models import LoreDocument, LoreHit, LoreQuery
from smeshariki_ai.rag.lore.services import LoadLore, SearchLore


def hit(document: str, score: float, *, rank: int = 1) -> LoreHit:
    return LoreHit(
        document_id=document,
        position=0,
        title="Эпизод",
        text=f"текст {document}",
        score=score,
        rank=rank,
    )


def write_package(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "package.yaml").write_text("format_version: 1\n", encoding="utf-8")
    documents = root / "documents"
    documents.mkdir()
    (documents / "d01.yaml").write_text(
        "id: d01\ntitle: Возврат\n"
        "text: |\n  Возврат оплаты на карту.\nsource: Синтетика\n",
        encoding="utf-8",
    )
    (documents / "d02.yaml").write_text(
        "id: d02\ntitle: Гольф\n"
        "text: |\n  Копатыч играет в гольф клюшкой.\nsource: Синтетика\n",
        encoding="utf-8",
    )


class StubDense:
    def __init__(
        self,
        hits: tuple[LoreHit, ...] = (),
        error: Exception | None = None,
    ) -> None:
        self._hits = hits
        self._error = error

    async def search(self, text: str, limit: int) -> tuple[LoreHit, ...]:
        if self._error is not None:
            raise self._error
        return self._hits


async def test_fake_embeddings_are_deterministic_and_normalised() -> None:
    provider = FakeEmbeddingProvider(dimension=8)

    first = await provider.embed(("Крош и Ёжик", "Нюша"))
    second = await provider.embed(("Крош и Ёжик", "Нюша"))

    assert first == second
    assert len(first[0]) == 8
    assert cosine(first[0], first[0]) == pytest.approx(1.0)
    assert cosine(first[0], first[1]) < 1.0


async def test_fake_query_embedding_uses_the_query_form() -> None:
    provider = FakeEmbeddingProvider(dimension=8)

    query = await provider.embed_query("Крош играет в футбол")
    passage = await provider.embed(("Крош играет в футбол",))

    assert len(query) == 8
    assert query != passage[0]


def test_fake_embeddings_reject_invalid_dimension() -> None:
    with pytest.raises(ValueError):
        FakeEmbeddingProvider(dimension=0)


async def test_local_query_embedding_uses_the_query_prefix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = LocalEmbeddingProvider()
    calls: list[str] = []

    async def ensured() -> None:
        return None

    def encode(texts, prefix="passage: "):
        calls.append(prefix)
        return tuple((0.0, 1.0) for _ in texts)

    monkeypatch.setattr(provider, "_ensure_model", ensured)
    monkeypatch.setattr(provider, "_encode", encode)

    await provider.embed_query("Крош")
    await provider.embed(("Крош",))

    assert calls == ["query: ", "passage: "]


async def test_local_embeddings_fail_cleanly_without_the_dependency(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = LocalEmbeddingProvider()

    async def missing() -> None:
        raise EmbeddingUnavailableError("transformers is not installed")

    monkeypatch.setattr(provider, "_ensure_model", missing)

    with pytest.raises(EmbeddingUnavailableError):
        await provider.embed(("Крош",))


def test_fuse_prefers_bm25_when_the_weight_is_one() -> None:
    bm25 = (hit("a", 9.0), hit("b", 5.0))
    dense = (hit("b", 0.9), hit("c", 0.8))

    fused = fuse_hits(bm25, dense, weight=1.0)

    assert [item.document_id for item in fused] == ["a", "b", "c"]
    assert fused[0].score == pytest.approx(9.0)


def test_fuse_prefers_dense_when_the_weight_is_zero() -> None:
    bm25 = (hit("a", 9.0), hit("b", 5.0))
    dense = (hit("b", 0.9), hit("c", 0.8))

    fused = fuse_hits(bm25, dense, weight=0.0)

    assert [item.document_id for item in fused] == ["b", "c", "a"]
    assert fused[0].score == pytest.approx(9.0)


def test_fuse_keeps_one_hit_per_document_and_bm25_scale() -> None:
    bm25 = (hit("a", 8.0), hit("b", 4.0))
    dense = (hit("a", 0.5), hit("a", 0.4), hit("c", 0.3))

    fused = fuse_hits(bm25, dense, weight=0.5)

    assert [item.document_id for item in fused] == ["a", "c", "b"]
    assert fused[0].score == pytest.approx(8.0)
    assert fused[-1].score <= fused[0].score


def test_fuse_without_candidates_returns_nothing() -> None:
    assert fuse_hits((), (), weight=0.7) == ()


def test_fuse_rejects_invalid_weight() -> None:
    with pytest.raises(ValueError):
        fuse_hits((), (), weight=1.5)


async def test_in_memory_dense_index_ranks_by_cosine() -> None:
    provider = FakeEmbeddingProvider(dimension=16)
    documents = (
        LoreDocument(id="d01", title="Футбол", text="Крош играет в футбол с мячом."),
        LoreDocument(id="d02", title="Гольф", text="Копатыч играет в гольф клюшкой."),
    )
    index = await InMemoryDenseIndex.build(provider, documents)

    hits = await index.search("футбол и мяч", limit=2)

    assert hits[0].document_id == "d01"
    assert hits[0].rank == 1
    assert hits[1].rank == 2


async def test_in_memory_dense_index_handles_an_empty_limit() -> None:
    provider = FakeEmbeddingProvider()
    documents = (LoreDocument(id="d01", title="Футбол", text="Крош играет в футбол."),)
    index = await InMemoryDenseIndex.build(provider, documents)

    assert await index.search("футбол", limit=0) == ()


def test_local_provider_exposes_model_metadata() -> None:
    provider = LocalEmbeddingProvider()

    assert provider.model_id == "intfloat/multilingual-e5-small"
    assert provider.dimension == 384


async def test_search_merges_dense_candidates(tmp_path: Path) -> None:
    write_package(tmp_path)
    index = InMemoryBm25Index()
    analyzer = SimpleAnalyzer()
    await LoadLore(analyzer).load(tmp_path, index)
    dense = StubDense(hits=(hit("d02", 0.9),))
    searcher = SearchLore(index, analyzer, dense=dense, hybrid_weight=0.5)

    result = await searcher.search(LoreQuery(text="возврат оплаты"))

    documents = [item.document_id for item in result.hits]
    assert documents == ["d01", "d02"]


async def test_search_degrades_to_bm25_when_dense_fails(tmp_path: Path) -> None:
    write_package(tmp_path)
    index = InMemoryBm25Index()
    analyzer = SimpleAnalyzer()
    await LoadLore(analyzer).load(tmp_path, index)
    dense = StubDense(error=RuntimeError("vector store is down"))
    searcher = SearchLore(index, analyzer, dense=dense)

    result = await searcher.search(LoreQuery(text="возврат оплаты"))

    assert [item.document_id for item in result.hits] == ["d01"]


def test_search_rejects_invalid_hybrid_weight() -> None:
    with pytest.raises(ValueError):
        SearchLore(InMemoryBm25Index(), SimpleAnalyzer(), hybrid_weight=2.0)
