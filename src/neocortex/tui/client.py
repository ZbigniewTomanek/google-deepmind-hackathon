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

    async def discover_domains(self) -> dict[str, Any]:
        """List semantic knowledge domains."""
        result = await self._client.call_tool("discover_domains", {})
        return self._parse_result(result)

    async def discover_graphs(self) -> dict[str, Any]:
        """List accessible knowledge graphs with stats."""
        result = await self._client.call_tool("discover_graphs", {})
        return self._parse_result(result)

    async def discover_ontology(self, graph_name: str) -> dict[str, Any]:
        """Get node/edge types for a specific graph."""
        result = await self._client.call_tool("discover_ontology", {"graph_name": graph_name})
        return self._parse_result(result)

    async def discover_details(self, type_name: str, graph_name: str, kind: str = "node") -> dict[str, Any]:
        """Get detailed info about a specific type in a graph."""
        result = await self._client.call_tool(
            "discover_details", {"type_name": type_name, "graph_name": graph_name, "kind": kind}
        )
        return self._parse_result(result)

    async def browse_nodes(self, graph_name: str, type_name: str | None = None, limit: int = 20) -> dict[str, Any]:
        """Browse actual node instances in a graph."""
        args: dict[str, Any] = {"graph_name": graph_name, "limit": limit}
        if type_name:
            args["type_name"] = type_name
        result = await self._client.call_tool("browse_nodes", args)
        return self._parse_result(result)

    async def inspect_node(self, node_name: str, graph_name: str) -> dict[str, Any]:
        """Inspect a node and its immediate neighborhood."""
        result = await self._client.call_tool("inspect_node", {"node_name": node_name, "graph_name": graph_name})
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
