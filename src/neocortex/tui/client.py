"""MCP client wrapper for communicating with a running NeoCortex server."""

from __future__ import annotations

import json
from typing import Any

from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport
from loguru import logger


class NeoCortexClient:
    """Async MCP client that talks to a NeoCortex server via streamable-HTTP transport."""

    def __init__(self, base_url: str = "http://localhost:8000", token: str | None = None):
        self._base_url = base_url.rstrip("/")
        self._token = token
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        transport = StreamableHttpTransport(url=f"{self._base_url}/mcp", headers=headers)
        self._client = Client(transport=transport)

    async def __aenter__(self) -> NeoCortexClient:
        await self._client.__aenter__()
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self._client.__aexit__(*args)

    async def remember(self, text: str, context: str | None = None) -> dict[str, Any]:
        """Store a memory via the remember tool."""
        arguments: dict[str, Any] = {"text": text}
        if context:
            arguments["context"] = context
        result = await self._client.call_tool("remember", arguments)
        return self._parse_result(result)

    async def recall(self, query: str, limit: int = 10) -> dict[str, Any]:
        """Recall memories matching a query."""
        result = await self._client.call_tool("recall", {"query": query, "limit": limit})
        return self._parse_result(result)

    async def discover(self) -> dict[str, Any]:
        """Discover ontology and graph statistics."""
        result = await self._client.call_tool("discover", {})
        return self._parse_result(result)

    @staticmethod
    def _parse_result(result: Any) -> dict[str, Any]:
        """Parse the MCP tool result into a dict."""
        if isinstance(result, dict):
            return result
        if hasattr(result, "structured_content") and isinstance(result.structured_content, dict):
            return result.structured_content
        if isinstance(result, list) and result:
            first = result[0]
            if hasattr(first, "text"):
                try:
                    return json.loads(first.text)
                except (json.JSONDecodeError, TypeError):
                    return {"raw": first.text}
            if isinstance(first, dict):
                return first
        try:
            return json.loads(str(result))
        except (json.JSONDecodeError, TypeError):
            logger.warning("Could not parse MCP result: {}", type(result).__name__)
            return {"raw": str(result)}
