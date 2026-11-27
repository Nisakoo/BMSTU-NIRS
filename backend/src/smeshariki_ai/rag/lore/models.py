"""Domain models of the BM25 lore search."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from smeshariki_ai.rag.models import NonEmptyText, Slug

_LORE_PACKAGE_FORMAT_VERSION = 1


class LoreModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class LoreDocument(LoreModel):
    """One narrative source document, independent of its search chunks."""

    id: Slug
    title: NonEmptyText
    text: NonEmptyText
    source: NonEmptyText | None = None
    continuity: Slug | None = None
    characters: tuple[Slug, ...] = ()
    tags: tuple[NonEmptyText, ...] = ()


class LoreChunk(LoreModel):
    """An indexed fragment of a document with its analyzed terms."""

    document_id: Slug
    position: int = Field(ge=0)
    text: NonEmptyText
    terms: tuple[NonEmptyText, ...] = ()
    # The length used by BM25 normalisation. It can differ from ``len(terms)``
    # when a field such as the title is indexed as a boost without making the
    # chunk look longer.
    length: int | None = Field(default=None, ge=0)

    @property
    def term_count(self) -> int:
        return len(self.terms) if self.length is None else self.length


class LoreEntry(LoreModel):
    document: LoreDocument
    chunks: tuple[LoreChunk, ...]


class LoreQuery(LoreModel):
    text: NonEmptyText
    top_k: int = Field(default=10, ge=1, le=100)
    tags: tuple[NonEmptyText, ...] = ()


class LoreHit(LoreModel):
    chunk_id: int | None = None
    document_id: Slug
    position: int = Field(ge=0)
    title: str
    source: str | None = None
    text: str
    score: float
    rank: int = Field(ge=1)


class LoreSearchResult(LoreModel):
    hits: tuple[LoreHit, ...] = ()
    total: int = Field(default=0, ge=0)
    version: int = Field(default=0, ge=0)


class LoreLoadSummary(LoreModel):
    version: int = Field(ge=0)
    document_count: int = Field(ge=0)
    chunk_count: int = Field(ge=0)
    term_count: int = Field(ge=0)


LORE_PACKAGE_FORMAT_VERSION = _LORE_PACKAGE_FORMAT_VERSION
