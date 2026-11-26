"""Configuration of the RAG module."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ExpansionMode = Literal["append", "replace"]


class RagConfig(BaseModel):
    """RAG switches; the values come from ``load_config`` only."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    # Off by default: the production Compose stack enables it explicitly.
    query_expansion_enabled: bool = False
    # ``replace`` wins on the golden set: better MRR and context recall.
    query_expansion_mode: ExpansionMode = "replace"
    lore_retrieval_k: int = Field(default=10, ge=1)
    lore_max_passages: int = Field(default=3, ge=1)
    lore_max_chars: int = Field(default=1600, ge=1)
    lore_min_score: float = Field(default=2.0, ge=0)
    # Off by default: reranking costs an extra LLM call per search.
    lore_rerank_enabled: bool = False


__all__ = ["ExpansionMode", "RagConfig"]
