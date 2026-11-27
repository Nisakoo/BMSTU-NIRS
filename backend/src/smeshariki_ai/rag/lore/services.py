"""Use cases of the BM25 lore search: loading and searching."""

from __future__ import annotations

import logging
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from smeshariki_ai.observability import log_event, utc_now
from smeshariki_ai.rag.lore.analyzer import TextAnalyzer
from smeshariki_ai.rag.lore.bm25 import Bm25Params
from smeshariki_ai.rag.lore.chunking import ChunkingConfig, chunk_text
from smeshariki_ai.rag.lore.hybrid import DenseSearcher, fuse_hits
from smeshariki_ai.rag.lore.models import (
    LoreChunk,
    LoreEntry,
    LoreHit,
    LoreLoadSummary,
    LoreQuery,
    LoreSearchResult,
)
from smeshariki_ai.rag.lore.package import (
    LorePackageInvalidError,
    check_package,
    iter_documents,
)
from smeshariki_ai.rag.lore.ports import (
    LoreIndex,
    LoreSchemaNotReadyError,
    LoreStore,
    LoreStoreError,
    LoreStoreUnavailableError,
)
from smeshariki_ai.rag.package import Issue

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class LoreConfig:
    chunking: ChunkingConfig = field(default_factory=ChunkingConfig)
    bm25: Bm25Params = field(default_factory=Bm25Params)


class LoreLoadReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    loaded: bool
    summary: LoreLoadSummary | None = None
    issues: tuple[Issue, ...] = ()
    duration_ms: int = Field(default=0, ge=0)


class SearchLore:
    def __init__(
        self,
        index: LoreIndex,
        analyzer: TextAnalyzer,
        config: LoreConfig | None = None,
        *,
        dense: DenseSearcher | None = None,
        hybrid_weight: float = 0.7,
    ) -> None:
        if not 0.0 <= hybrid_weight <= 1.0:
            raise ValueError("hybrid_weight must be between 0 and 1")
        self._index = index
        self._analyzer = analyzer
        self._config = config or LoreConfig()
        self._dense = dense
        self._hybrid_weight = hybrid_weight

    async def search(self, query: LoreQuery) -> LoreSearchResult:
        started_at = utc_now()
        started = time.monotonic()
        terms = self.analyze(query.text)
        try:
            hits = (
                await self._index.search(
                    terms, query.top_k, self._config.bm25, query.tags
                )
                if terms
                else ()
            )
            version = await self._index.version()
            if self._dense is not None:
                hits = await self._fuse(query, hits)
        except LoreStoreError as error:
            log_event(
                logger,
                logging.WARNING,
                "lore.search.completed",
                started_at=started_at,
                duration_ms=round((time.monotonic() - started) * 1000, 3),
                outcome="failed",
                match_count=0,
                query_term_count=len(terms),
                error_type=type(error).__name__,
            )
            raise
        log_event(
            logger,
            logging.INFO,
            "lore.search.completed",
            started_at=started_at,
            duration_ms=round((time.monotonic() - started) * 1000, 3),
            outcome="found" if hits else "empty",
            match_count=len(hits),
            hit_count=len(hits),
            query_term_count=len(terms),
            top_score=round(hits[0].score, 3) if hits else None,
            index_version=version,
        )
        return LoreSearchResult(hits=hits, total=len(hits), version=version)

    def analyze(self, text: str) -> tuple[str, ...]:
        """Analyze a query the same way documents were analyzed."""

        return self._analyzer.terms(text)

    async def _fuse(
        self, query: LoreQuery, hits: tuple[LoreHit, ...]
    ) -> tuple[LoreHit, ...]:
        """Merge BM25 hits with dense candidates, falling back on BM25 alone."""

        dense = self._dense
        if dense is None:
            return hits
        try:
            dense_hits = await dense.search(query.text, query.top_k * 4)
        except Exception as error:  # noqa: BLE001 - dense side is optional
            log_event(
                logger,
                logging.WARNING,
                "lore.search.degraded",
                started_at=utc_now(),
                duration_ms=0.0,
                outcome="degraded",
                error_type=type(error).__name__,
            )
            return hits
        if not dense_hits:
            return hits
        return fuse_hits(hits, dense_hits, weight=self._hybrid_weight)


class LoadLore:
    def __init__(
        self,
        analyzer: TextAnalyzer,
        config: LoreConfig | None = None,
    ) -> None:
        self._analyzer = analyzer
        self._config = config or LoreConfig()

    async def load(self, root: Path, store: LoreStore) -> LoreLoadReport:
        started_at = utc_now()
        started = time.monotonic()
        check = check_package(root)
        if not check.valid:
            report = LoreLoadReport(loaded=False, issues=check.issues)
            self._log(report, started_at, started, outcome="rejected")
            return report

        try:
            summary = await store.replace(self._entries(root))
        except LorePackageInvalidError as error:
            report = LoreLoadReport(loaded=False, issues=error.issues)
            self._log(report, started_at, started, outcome="rejected")
            return report
        except LoreSchemaNotReadyError as error:
            report = self._failed(
                "schema_not_ready",
                "таблицы lore не созданы: примените миграции (make migrate)",
            )
            self._log(
                report,
                started_at,
                started,
                outcome="failed",
                error_type=type(error).__name__,
            )
            return report
        except LoreStoreUnavailableError as error:
            report = self._failed("database_unavailable", "база данных лора недоступна")
            self._log(
                report,
                started_at,
                started,
                outcome="failed",
                error_type=type(error).__name__,
            )
            return report
        except LoreStoreError as error:
            report = self._failed(
                "stored_data_invalid",
                "данные лора в БД не проходят проверку моделей",
            )
            self._log(
                report,
                started_at,
                started,
                outcome="failed",
                error_type=type(error).__name__,
            )
            return report

        report = LoreLoadReport(
            loaded=True,
            summary=summary,
            duration_ms=_milliseconds(started),
        )
        self._log(report, started_at, started, outcome="loaded")
        return report

    def _entries(self, root: Path) -> Iterator[LoreEntry]:
        for document in iter_documents(root):
            title_terms = self._analyzer.terms(document.title)
            chunks = []
            for position, text in enumerate(
                chunk_text(document.text, self._config.chunking)
            ):
                terms, length = self._chunk_terms(position, title_terms, text)
                chunks.append(
                    LoreChunk(
                        document_id=document.id,
                        position=position,
                        text=text,
                        terms=terms,
                        length=length,
                    )
                )
            yield LoreEntry(document=document, chunks=tuple(chunks))

    def _chunk_terms(
        self,
        position: int,
        title_terms: tuple[str, ...],
        text: str,
    ) -> tuple[tuple[str, ...], int]:
        """Return the indexed terms and the BM25 length of the chunk.

        The title is repeated in the first chunk as a field boost: the repeated
        terms raise ``tf`` (bounded by BM25 saturation), while ``length`` stays
        the length of the text so the chunk is not punished as if it were
        longer.
        """

        text_terms = self._analyzer.terms(text)
        length = len(text_terms)
        if position != 0 or not title_terms:
            return text_terms, length
        return (*title_terms, *title_terms, *text_terms), length

    @staticmethod
    def _failed(code: str, message: str) -> LoreLoadReport:
        return LoreLoadReport(
            loaded=False,
            issues=(Issue(file=".", code=code, message=message),),
        )

    @staticmethod
    def _log(
        report: LoreLoadReport,
        started_at: str,
        started: float,
        *,
        outcome: str,
        error_type: str | None = None,
    ) -> None:
        summary = report.summary
        log_event(
            logger,
            logging.WARNING if outcome != "loaded" else logging.INFO,
            "lore.load.completed",
            started_at=started_at,
            duration_ms=round((time.monotonic() - started) * 1000, 3),
            outcome=outcome,
            document_count=0 if summary is None else summary.document_count,
            chunk_count=0 if summary is None else summary.chunk_count,
            term_count=0 if summary is None else summary.term_count,
            index_version=0 if summary is None else summary.version,
            error_type=error_type,
        )


def _milliseconds(started: float) -> int:
    return max(0, round((time.monotonic() - started) * 1000))
