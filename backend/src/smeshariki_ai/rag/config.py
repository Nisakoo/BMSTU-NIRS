"""Configuration of the RAG module."""

from pydantic import BaseModel, ConfigDict


class RagConfig(BaseModel):
    """RAG switches; the values come from ``load_config`` only."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    # Off by default: the production Compose stack enables it explicitly.
    query_expansion_enabled: bool = False


__all__ = ["RagConfig"]
