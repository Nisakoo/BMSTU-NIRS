"""Agent tool of the BM25 lore search: a bounded reference block, not a plot."""

from __future__ import annotations

from typing import Annotated, Any, ClassVar

from pydantic import BaseModel, ConfigDict, StringConstraints

from smeshariki_ai.agent.tools import Tool
from smeshariki_ai.rag.lore.context import LoreContextBuilder
from smeshariki_ai.rag.lore.models import LoreQuery
from smeshariki_ai.rag.lore.ports import LoreStoreError
from smeshariki_ai.rag.lore.services import SearchLore

UNAVAILABLE_MESSAGE = (
    "База лора сейчас недоступна. Продолжай по идее пользователя и не выдавай "
    "придуманные факты за канонические."
)


class SearchLoreArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)
    ]


class SearchLoreTool(Tool):
    name: ClassVar[str] = "search_lore"
    description: ClassVar[str] = (
        "Search narrative Smeshariki lore: scenes, episode summaries and story "
        "patterns. Use it at most once per story, only when the user's premise "
        "needs a canon detail or the tone of the original. Treat the passages "
        "as reference material, not as a plot to copy: do not retell them, do "
        "not enumerate facts, locations, items or relationships, and do not "
        "mention sources in the story. Use at most two or three details that "
        "the premise really needs. If status is empty or unavailable, continue "
        "with the user's idea and do not present invented facts as canon."
    )
    arguments_model: ClassVar[type[BaseModel]] = SearchLoreArguments

    def __init__(
        self,
        search: SearchLore,
        context: LoreContextBuilder | None = None,
    ) -> None:
        self._search = search
        self._context = context or LoreContextBuilder()

    async def execute(self, arguments: BaseModel) -> dict[str, Any]:
        assert isinstance(arguments, SearchLoreArguments)
        try:
            result = await self._search.search(
                LoreQuery(text=arguments.query, top_k=self._context.retrieval_k)
            )
        except LoreStoreError:
            return {
                "status": "unavailable",
                "passages": [],
                "message": UNAVAILABLE_MESSAGE,
            }

        context = self._context.build(result)
        return {
            "status": context.status,
            "passages": [
                passage.model_dump(mode="json") for passage in context.passages
            ],
            "message": context.message,
        }
