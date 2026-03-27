from __future__ import annotations

import math
import os

from loguru import logger


class EmbeddingService:
    """Async embedding service using Gemini Embedding via google-genai SDK.

    Generates 768-dim normalized embeddings with MRL truncation.
    Gracefully returns None when GOOGLE_API_KEY is unavailable or on API errors.
    """

    def __init__(self, model: str | None = None, dimensions: int = 768) -> None:
        self._model = model or "gemini-embedding-001"
        self._dimensions = dimensions
        self._client = None

        api_key = os.environ.get("GOOGLE_API_KEY")
        if api_key:
            from google import genai

            self._client = genai.Client(api_key=api_key)
            logger.info("EmbeddingService initialized with model={}", self._model)
        else:
            logger.warning("GOOGLE_API_KEY not set — EmbeddingService will return None for all embed calls")

    async def embed(self, text: str) -> list[float] | None:
        """Embed a single text string. Returns normalized 768-dim vector or None."""
        if self._client is None:
            return None

        try:
            from google.genai import types

            response = await self._client.aio.models.embed_content(
                model=self._model,
                contents=text,
                config=types.EmbedContentConfig(output_dimensionality=self._dimensions),
            )
            embeddings = response.embeddings
            if not embeddings:
                return None
            values = embeddings[0].values
            if values is None:
                return None
            return self._normalize(list(values))
        except Exception:
            logger.opt(exception=True).warning("Embedding API call failed for text (length={})", len(text))
            return None

    async def embed_batch(self, texts: list[str]) -> list[list[float] | None]:
        """Embed multiple texts in a single API call. Returns list of normalized vectors."""
        if self._client is None:
            return [None] * len(texts)

        try:
            from google.genai import types

            response = await self._client.aio.models.embed_content(
                model=self._model,
                contents=texts,
                config=types.EmbedContentConfig(output_dimensionality=self._dimensions),
            )
            embeddings = response.embeddings
            if not embeddings:
                return [None] * len(texts)
            return [self._normalize(list(emb.values)) if emb.values is not None else None for emb in embeddings]
        except Exception:
            logger.opt(exception=True).warning("Batch embedding API call failed for {} texts", len(texts))
            return [None] * len(texts)

    @staticmethod
    def _normalize(vector: list[float]) -> list[float]:
        """L2-normalize a vector to unit length."""
        norm = math.sqrt(sum(x * x for x in vector))
        if norm == 0:
            return vector
        return [x / norm for x in vector]
