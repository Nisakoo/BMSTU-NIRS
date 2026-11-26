"""Agent tool of the BM25 lore search: a bounded reference block, not a plot."""

from __future__ import annotations

import logging
import time
from typing import Annotated, Any, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, StringConstraints

from smeshariki_ai.agent.tools import Tool
from smeshariki_ai.observability import log_event, utc_now
from smeshariki_ai.rag.lore.context import LoreContextBuilder
from smeshariki_ai.rag.lore.expansion import QueryExpander
from smeshariki_ai.rag.lore.models import LoreQuery
from smeshariki_ai.rag.lore.ports import LoreStoreError
from smeshariki_ai.rag.lore.services import SearchLore

logger = logging.getLogger(__name__)

UNAVAILABLE_MESSAGE = (
    "База лора сейчас недоступна. Продолжай по идее пользователя и не выдавай "
    "придуманные факты за канонические."
)

LoreMode = Literal["any", "style", "plot", "facts"]
ExpansionMode = Literal["append", "replace"]
_MODE_TAGS: dict[str, tuple[str, ...]] = {
    "any": (),
    "style": ("style", "dialogue"),
    "plot": ("plot",),
    "facts": ("facts",),
}


class SearchLoreArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)
    ]
    mode: LoreMode = "any"


class SearchLoreTool(Tool):
    name: ClassVar[str] = "search_lore"
    description: ClassVar[str] = (
        "Search narrative Smeshariki lore: scenes, episode summaries and story "
        "patterns. Use it at most once per story, only when the user's premise "
        "needs a canon detail, a dialogue example or the tone of the original. "
        "Set mode to style for dialogue and voice examples, to plot for story "
        "moves, to facts for concrete lore details, or leave any. Treat the "
        "passages as reference material, not as a plot to copy: do not retell "
        "them, do not enumerate facts, locations, items or relationships, and "
        "do not mention sources in the story. Use at most two or three details "
        "that the premise really needs. If status is empty or unavailable, "
        "continue with the user's idea and do not present invented facts as "
        "canon."
    )
    arguments_model: ClassVar[type[BaseModel]] = SearchLoreArguments

    def __init__(
        self,
        search: SearchLore,
        context: LoreContextBuilder | None = None,
        expander: QueryExpander | None = None,
        expansion_mode: ExpansionMode = "replace",
    ) -> None:
        self._search = search
        self._context = context or LoreContextBuilder()
        self._expander = expander
        self._expansion_mode = expansion_mode

    async def execute(self, arguments: BaseModel) -> dict[str, Any]:
        assert isinstance(arguments, SearchLoreArguments)
        started_at = utc_now()
        started = time.monotonic()
        expanded = (
            ()
            if self._expander is None
            else await self._expander.expand(arguments.query)
        )
        # The original query is kept by default: expansion only adds signal.
        # ``replace`` searches by the keywords alone, which ranks the first
        # relevant document higher on the golden set.
        if not expanded:
            search_text = arguments.query
        elif self._expansion_mode == "replace":
            search_text = " ".join(expanded)
        else:
            search_text = f"{arguments.query} {' '.join(expanded)}"
        # The "names only" rule looks at the original query, so an expansion
        # cannot turn a bare character name into a story premise.
        original_terms = self._search.analyze(arguments.query)
        terms = self._search.analyze(search_text)
        try:
            result = await self._search.search(
                LoreQuery(
                    text=search_text,
                    top_k=self._context.retrieval_k,
                    tags=_MODE_TAGS[arguments.mode],
                )
            )
        except LoreStoreError:
            log_event(
                logger,
                logging.WARNING,
                "lore.tool.completed",
                started_at=started_at,
                duration_ms=round((time.monotonic() - started) * 1000, 3),
                outcome="unavailable",
                match_count=0,
                hit_count=0,
                passage_count=0,
                context_chars=0,
                query_term_count=len(terms),
            )
            return {
                "status": "unavailable",
                "passages": [],
                "message": UNAVAILABLE_MESSAGE,
            }

        context = self._context.build(result, query_terms=original_terms)
        log_event(
            logger,
            logging.INFO,
            "lore.tool.completed",
            started_at=started_at,
            duration_ms=round((time.monotonic() - started) * 1000, 3),
            outcome=context.status,
            match_count=result.total,
            hit_count=result.total,
            passage_count=len(context.passages),
            context_chars=sum(len(passage.text) for passage in context.passages),
            query_term_count=len(terms),
        )
        return {
            "status": context.status,
            "passages": [
                passage.model_dump(mode="json") for passage in context.passages
            ],
            "message": context.message,
        }
