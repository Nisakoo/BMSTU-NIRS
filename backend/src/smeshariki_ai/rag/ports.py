from __future__ import annotations

from typing import Protocol

from smeshariki_ai.rag.models import (
    EntityType,
    KnowledgeRecord,
    SystemContext,
)


class StructuredKnowledgeStorePort(Protocol):
    def load_system_context(self) -> SystemContext: ...

    def load_records(self) -> tuple[KnowledgeRecord, ...]: ...

    def find(
        self,
        entity_type: EntityType,
        normalized_key: str,
        canon_variants: tuple[str, ...],
    ) -> tuple[KnowledgeRecord, ...]: ...
