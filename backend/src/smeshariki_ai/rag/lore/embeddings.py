from __future__ import annotations

import asyncio
import hashlib
import math
from collections.abc import Sequence
from typing import Protocol

DEFAULT_MODEL = "intfloat/multilingual-e5-small"
DEFAULT_DIMENSION = 384


class EmbeddingUnavailableError(RuntimeError):
    """The embedding model cannot be used in this environment."""


class EmbeddingProvider(Protocol):
    """Turns texts into unit vectors for the dense retrieval side."""

    model_id: str
    dimension: int

    async def embed(self, texts: Sequence[str]) -> tuple[tuple[float, ...], ...]: ...

    async def embed_query(self, text: str) -> tuple[float, ...]: ...


class FakeEmbeddingProvider:
    """Deterministic hashing embeddings for tests and offline runs."""

    model_id = "fake"

    def __init__(self, dimension: int = 16) -> None:
        if dimension <= 0:
            raise ValueError("dimension must be positive")
        self.dimension = dimension

    async def embed(self, texts: Sequence[str]) -> tuple[tuple[float, ...], ...]:
        return tuple(self._vector(text) for text in texts)

    async def embed_query(self, text: str) -> tuple[float, ...]:
        return self._vector(f"query {text}")

    def _vector(self, text: str) -> tuple[float, ...]:
        values = [0.0] * self.dimension
        for token in text.casefold().split():
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            for offset in range(0, len(digest), 2):
                index = digest[offset] % self.dimension
                sign = 1.0 if digest[offset + 1] % 2 else -1.0
                values[index] += sign
        length = math.sqrt(sum(value * value for value in values))
        if length == 0:
            return tuple(values)
        return tuple(value / length for value in values)


class LocalEmbeddingProvider:
    """Multilingual e5 embeddings through ``transformers``.

    The dependency is optional and imported lazily, so the BM25 path and the
    test suite work without it. Loading the model happens once per process.
    """

    def __init__(
        self,
        model_id: str = DEFAULT_MODEL,
        *,
        dimension: int = DEFAULT_DIMENSION,
    ) -> None:
        self.model_id = model_id
        self.dimension = dimension
        self._tokenizer = None
        self._model = None
        self._lock = asyncio.Lock()

    async def embed(self, texts: Sequence[str]) -> tuple[tuple[float, ...], ...]:
        if not texts:
            return ()
        await self._ensure_model()
        return await asyncio.to_thread(self._encode, tuple(texts))

    async def _ensure_model(self) -> None:
        if self._model is not None:
            return
        async with self._lock:
            if self._model is not None:
                return
            try:
                from transformers import AutoModel, AutoTokenizer
            except ImportError as error:
                raise EmbeddingUnavailableError(
                    "transformers is not installed; add it with uv add transformers"
                ) from error
            try:
                self._tokenizer = await asyncio.to_thread(
                    AutoTokenizer.from_pretrained, self.model_id
                )
                self._model = await asyncio.to_thread(
                    AutoModel.from_pretrained, self.model_id
                )
                self._model.eval()
            except Exception as error:  # noqa: BLE001 - model loading is external
                raise EmbeddingUnavailableError(
                    "the embedding model could not be loaded"
                ) from error

    def _encode(
        self, texts: tuple[str, ...], prefix: str = "passage: "
    ) -> tuple[tuple[float, ...], ...]:
        import torch

        prepared = [f"{prefix}{text}" for text in texts]
        tokenized = self._tokenizer(
            prepared,
            padding=True,
            truncation=True,
            max_length=512,
            return_tensors="pt",
        )
        with torch.no_grad():
            hidden = self._model(**tokenized).last_hidden_state
        mask = tokenized["attention_mask"].unsqueeze(-1).float()
        summed = (hidden * mask).sum(dim=1)
        counts = mask.sum(dim=1).clamp(min=1e-9)
        normalised = torch.nn.functional.normalize(summed / counts, p=2, dim=1)
        return tuple(tuple(float(value) for value in row) for row in normalised)

    async def embed_query(self, text: str) -> tuple[float, ...]:
        """Embed a query with the e5 ``query:`` prefix, not ``passage:``."""

        await self._ensure_model()
        return (await asyncio.to_thread(self._encode, (text,), "query: "))[0]


def cosine(left: Sequence[float], right: Sequence[float]) -> float:
    return sum(a * b for a, b in zip(left, right, strict=True))
