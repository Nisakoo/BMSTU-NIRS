from __future__ import annotations

from collections.abc import Iterable

from smeshariki_ai.rag.models import (
    EntityType,
    KnowledgeCatalog,
    KnowledgeRecord,
    SystemContext,
    normalize_lookup_key,
)


class InMemoryStructuredKnowledgeStore:
    def __init__(
        self,
        *,
        system_context: SystemContext,
        records: Iterable[KnowledgeRecord],
    ) -> None:
        catalog = KnowledgeCatalog(schema_version="in-memory", records=tuple(records))
        self._system_context = system_context
        self._records = catalog.records
        self.load_system_context_calls = 0
        self.load_records_calls = 0

    def load_system_context(self) -> SystemContext:
        self.load_system_context_calls += 1
        return self._system_context

    def load_records(self) -> tuple[KnowledgeRecord, ...]:
        self.load_records_calls += 1
        return self._records

    def find(
        self,
        entity_type: EntityType,
        normalized_key: str,
        canon_variants: tuple[str, ...],
    ) -> tuple[KnowledgeRecord, ...]:
        requested_variants = set(canon_variants)
        matches: list[KnowledgeRecord] = []
        for record in self._records:
            if record.entity_type != entity_type:
                continue
            keys = (record.id, record.name, *record.aliases)
            if normalized_key not in {normalize_lookup_key(key) for key in keys}:
                continue
            record_variants = {
                normalize_lookup_key(variant) for variant in record.canon_variants
            }
            if requested_variants and requested_variants.isdisjoint(record_variants):
                continue
            matches.append(record)
        return tuple(matches)
