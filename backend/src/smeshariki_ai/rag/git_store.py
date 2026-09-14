from __future__ import annotations

from pathlib import Path
import re

from pydantic import ValidationError

from smeshariki_ai.rag.in_memory import InMemoryStructuredKnowledgeStore
from smeshariki_ai.rag.models import KnowledgeCatalog, SystemContext


_VERSION_MARKER = re.compile(
    r"<!--\s*system-context-version:\s*(?P<version>[^\s]+)\s*-->"
)


class StructuredKnowledgeLoadError(RuntimeError):
    """Raised when Git-backed knowledge cannot be loaded as one valid snapshot."""


class GitStructuredKnowledgeStore(InMemoryStructuredKnowledgeStore):
    def __init__(self, context_path: Path, knowledge_path: Path) -> None:
        try:
            context_text = context_path.read_text(encoding="utf-8")
            system_context = self._parse_system_context(context_text)
            catalog = KnowledgeCatalog.model_validate_json(
                knowledge_path.read_text(encoding="utf-8")
            )
        except (OSError, UnicodeError, ValidationError, ValueError) as error:
            source = "knowledge" if knowledge_path.name in str(error) else "sources"
            if isinstance(error, ValidationError):
                source = "knowledge"
            raise StructuredKnowledgeLoadError(
                f"Unable to load structured knowledge {source}: {error}"
            ) from error

        super().__init__(system_context=system_context, records=catalog.records)

    @classmethod
    def default(cls) -> GitStructuredKnowledgeStore:
        data_directory = Path(__file__).with_name("data")
        return cls(
            data_directory / "system_context.md",
            data_directory / "knowledge.json",
        )

    @staticmethod
    def _parse_system_context(content: str) -> SystemContext:
        first_line, separator, prompt = content.partition("\n")
        match = _VERSION_MARKER.fullmatch(first_line)
        if not match or not separator:
            raise ValueError("system context version marker is missing or invalid")
        return SystemContext(version=match.group("version"), prompt=prompt)
