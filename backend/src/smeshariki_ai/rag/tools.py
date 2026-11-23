"""Agent tools of RAG: the inbound adapter between the agent and use cases."""

from typing import Annotated, Any, ClassVar

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from smeshariki_ai.agent.tools import Tool
from smeshariki_ai.rag.lookup import KnowledgeLookup
from smeshariki_ai.rag.models import Slug
from smeshariki_ai.rag.story_canon import StoryCanonLookup, StoryName


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
        "with the canonical facts for each continuity. If the result contains "
        "suggestions, retry with one of their exact names. If the status is "
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


class StoryCanonArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")

    names: Annotated[tuple[StoryName, ...], Field(min_length=1, max_length=3)]
    continuity: Slug | None = None


class GetStoryCanonTool(Tool):
    name: ClassVar[str] = "get_story_canon"
    description: ClassVar[str] = (
        "Get a compact story profile for one to three named Smeshariki "
        "characters. Use it when writing a story, at most once per story. It "
        "returns only age group, traits, speech style, catchphrases and the "
        "type of each relationship; it never returns free-text descriptions, "
        "sources, places, items or episodes. Treat the profile as a constraint "
        "on character and speech, not as a plot or a list of facts to mention: "
        "do not enumerate relationships and do not add props from it unless "
        "the user asks. For a story scene, object or place, call search_lore "
        "once as well; for factual questions use lookup_knowledge. If status "
        "is not_found or unavailable, continue with the user's idea and do "
        "not invent canon."
    )
    arguments_model: ClassVar[type[BaseModel]] = StoryCanonArguments

    def __init__(self, lookup: StoryCanonLookup) -> None:
        self._lookup = lookup

    async def execute(self, arguments: BaseModel) -> dict[str, Any]:
        assert isinstance(arguments, StoryCanonArguments)
        result = await self._lookup.lookup(arguments.names, arguments.continuity)
        return result.model_dump(mode="json", by_alias=True)
