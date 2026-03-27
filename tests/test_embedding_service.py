import math
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from neocortex.embedding_service import EmbeddingService


class TestNormalize:
    def test_normalize_produces_unit_vector(self):
        vector = [3.0, 4.0]
        result = EmbeddingService._normalize(vector)
        norm = math.sqrt(sum(x * x for x in result))
        assert abs(norm - 1.0) < 1e-9

    def test_normalize_high_dimensional(self):
        vector = [float(i) for i in range(1, 769)]
        result = EmbeddingService._normalize(vector)
        norm = math.sqrt(sum(x * x for x in result))
        assert abs(norm - 1.0) < 1e-9
        assert len(result) == 768

    def test_normalize_zero_vector_returns_zero(self):
        vector = [0.0, 0.0, 0.0]
        result = EmbeddingService._normalize(vector)
        assert result == [0.0, 0.0, 0.0]

    def test_normalize_already_unit(self):
        vector = [1.0, 0.0, 0.0]
        result = EmbeddingService._normalize(vector)
        assert abs(result[0] - 1.0) < 1e-9
        assert abs(result[1]) < 1e-9
        assert abs(result[2]) < 1e-9


class TestEmbedNoApiKey:
    @pytest.mark.asyncio
    async def test_embed_returns_none_when_no_api_key(self):
        with patch.dict("os.environ", {}, clear=True):
            # Remove GOOGLE_API_KEY if present
            import os

            env = os.environ.copy()
            env.pop("GOOGLE_API_KEY", None)
            with patch.dict("os.environ", env, clear=True):
                svc = EmbeddingService()
                result = await svc.embed("hello world")
                assert result is None

    @pytest.mark.asyncio
    async def test_embed_batch_returns_nones_when_no_api_key(self):
        with patch.dict("os.environ", {}, clear=True):
            import os

            env = os.environ.copy()
            env.pop("GOOGLE_API_KEY", None)
            with patch.dict("os.environ", env, clear=True):
                svc = EmbeddingService()
                result = await svc.embed_batch(["hello", "world"])
                assert result == [None, None]


class TestEmbedWithMockedClient:
    @pytest.mark.asyncio
    async def test_embed_returns_normalized_vector(self):
        raw_values = [3.0, 4.0] + [0.0] * 766
        expected_norm = math.sqrt(sum(x * x for x in raw_values))
        expected = [x / expected_norm for x in raw_values]

        mock_embedding = MagicMock()
        mock_embedding.values = raw_values

        mock_response = MagicMock()
        mock_response.embeddings = [mock_embedding]

        mock_client = MagicMock()
        mock_client.aio.models.embed_content = AsyncMock(return_value=mock_response)

        svc = EmbeddingService.__new__(EmbeddingService)
        svc._model = "test-model"
        svc._dimensions = 768
        svc._client = mock_client

        result = await svc.embed("test text")
        assert result is not None
        assert len(result) == 768
        norm = math.sqrt(sum(x * x for x in result))
        assert abs(norm - 1.0) < 1e-9
        for a, b in zip(result, expected, strict=False):
            assert abs(a - b) < 1e-9

    @pytest.mark.asyncio
    async def test_embed_batch_returns_multiple_vectors(self):
        raw1 = [1.0, 0.0, 0.0]
        raw2 = [0.0, 1.0, 0.0]

        mock_emb1 = MagicMock()
        mock_emb1.values = raw1
        mock_emb2 = MagicMock()
        mock_emb2.values = raw2

        mock_response = MagicMock()
        mock_response.embeddings = [mock_emb1, mock_emb2]

        mock_client = MagicMock()
        mock_client.aio.models.embed_content = AsyncMock(return_value=mock_response)

        svc = EmbeddingService.__new__(EmbeddingService)
        svc._model = "test-model"
        svc._dimensions = 768
        svc._client = mock_client

        result = await svc.embed_batch(["text1", "text2"])
        assert len(result) == 2
        assert result[0] is not None
        assert result[1] is not None
        # Each should be normalized
        for vec in result:
            norm = math.sqrt(sum(x * x for x in vec))
            assert abs(norm - 1.0) < 1e-9

    @pytest.mark.asyncio
    async def test_embed_returns_none_on_api_error(self):
        mock_client = MagicMock()
        mock_client.aio.models.embed_content = AsyncMock(side_effect=RuntimeError("API error"))

        svc = EmbeddingService.__new__(EmbeddingService)
        svc._model = "test-model"
        svc._dimensions = 768
        svc._client = mock_client

        result = await svc.embed("test text")
        assert result is None

    @pytest.mark.asyncio
    async def test_embed_batch_returns_nones_on_api_error(self):
        mock_client = MagicMock()
        mock_client.aio.models.embed_content = AsyncMock(side_effect=RuntimeError("API error"))

        svc = EmbeddingService.__new__(EmbeddingService)
        svc._model = "test-model"
        svc._dimensions = 768
        svc._client = mock_client

        result = await svc.embed_batch(["a", "b", "c"])
        assert result == [None, None, None]
