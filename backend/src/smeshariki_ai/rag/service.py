from __future__ import annotations

from smeshariki_ai.rag.models import (
    EntityType,
    KnowledgeAmbiguous,
    KnowledgeFound,
    KnowledgeLookupRequest,
    KnowledgeLookupResult,
    KnowledgeNotFound,
    KnowledgeRef,
    SystemContext,
    normalize_lookup_key,
)
from smeshariki_ai.rag.ports import StructuredKnowledgeStorePort


class StructuredKnowledgeService:
    def __init__(self, store: StructuredKnowledgeStorePort) -> None:
        self._store = store
        self._system_context: SystemContext | None = None

    def get_system_context(self) -> SystemContext:
        if self._system_context is None:
            self._system_context = self._store.load_system_context()
        return self._system_context

    def lookup_knowledge(
        self,
        entity_type: EntityType,
        key: str,
        canon_variants: tuple[str, ...] = (),
    ) -> KnowledgeLookupResult:
        request = KnowledgeLookupRequest(
            entity_type=entity_type,
            key=key,
            canon_variants=canon_variants,
        )
        normalized_key = normalize_lookup_key(request.key)
        normalized_variants = tuple(
            sorted({normalize_lookup_key(value) for value in request.canon_variants})
        )
        raw_matches = self._store.find(
            request.entity_type,
            normalized_key,
            normalized_variants,
        )
        unique_matches = {
            (EntityType(record.entity_type), record.id): record for record in raw_matches
        }
        matches = tuple(
            unique_matches[item]
            for item in sorted(
                unique_matches,
                key=lambda record_key: (record_key[0].value, record_key[1]),
            )
        )

        if not matches:
            return KnowledgeNotFound(
                entity_type=request.entity_type,
                key=normalized_key,
                canon_variants=normalized_variants,
            )
        if len(matches) == 1:
            return KnowledgeFound(entity=matches[0])

        candidates = tuple(
            KnowledgeRef(
                entity_type=EntityType(record.entity_type),
                id=record.id,
                name=record.name,
                canon_variants=record.canon_variants,
            )
            for record in matches
        )
        return KnowledgeAmbiguous(
            entity_type=request.entity_type,
            key=normalized_key,
            canon_variants=normalized_variants,
            candidates=candidates,
        )
