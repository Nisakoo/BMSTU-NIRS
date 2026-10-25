"""Agent tools of RAG: the inbound adapter between the agent and use cases."""

from typing import Annotated, Any, ClassVar

from pydantic import BaseModel, ConfigDict, StringConstraints

from smeshariki_ai.agent.tools import Tool
from smeshariki_ai.rag.lookup import KnowledgeLookup


class LookupKnowledgeArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)
    ]


class LookupKnowledgeTool(Tool):
    name: ClassVar[str] = "lookup_knowledge"
    description: ClassVar[str] = (
        "Look up canonical Smeshariki knowledge: a character, place, item or "
        "episode by its exact name, nickname or episode title. Call it before "
        "describing a hero's character, speech, relationships, a place, an "
        "item's abilities or the events of an episode. The result holds cards "
        "with the canonical facts for each continuity. If the status is "
        "not_found or unavailable, do not present invented facts as canon."
    )
    arguments_model: ClassVar[type[BaseModel]] = LookupKnowledgeArguments

    def __init__(self, lookup: KnowledgeLookup) -> None:
        self._lookup = lookup

    async def execute(self, arguments: BaseModel) -> dict[str, Any]:
        assert isinstance(arguments, LookupKnowledgeArguments)
        result = await self._lookup.lookup(arguments.name)
        # Aliases keep the field names of the package format, such as "from".
        return result.model_dump(mode="json", by_alias=True)
