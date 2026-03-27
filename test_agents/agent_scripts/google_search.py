#!/usr/bin/env python3
"""Google/web search tool (mock implementation)."""

from pydantic import BaseModel, Field

from open_agent_compiler.runtime import ScriptTool


class GoogleSearchInput(BaseModel):
    query: str = Field(description="Search query for Google")
    max_results: int = Field(default=5, description="Maximum number of results to return")


class GoogleSearchOutput(BaseModel):
    results: list[dict]
    query: str
    total_found: int


_MOCK_RESULTS = [
    {
        "title": "Python 3.13 Release Notes",
        "url": "https://docs.python.org/3.13/whatsnew/",
        "snippet": "Python 3.13 introduces free-threaded mode, improved error messages, and a new REPL.",
    },
    {
        "title": "MCP Protocol Specification",
        "url": "https://modelcontextprotocol.io/docs/spec",
        "snippet": "The Model Context Protocol (MCP) provides a standard way for AI models to access tools and data.",
    },
    {
        "title": "FastAPI Documentation",
        "url": "https://fastapi.tiangolo.com",
        "snippet": "FastAPI is a modern, fast web framework for building APIs with Python based on type hints.",
    },
    {
        "title": "PostgreSQL Knowledge Graph Patterns",
        "url": "https://example.com/pg-knowledge-graphs",
        "snippet": "Learn how to implement knowledge graphs using PostgreSQL with recursive CTEs and JSONB.",
    },
    {
        "title": "AI Agent Orchestration Best Practices",
        "url": "https://example.com/agent-orchestration",
        "snippet": "Multi-agent systems require careful orchestration for reliable tool use and context passing.",
    },
    {
        "title": "OpenCode Agent Framework",
        "url": "https://example.com/opencode",
        "snippet": "OpenCode provides a runtime for executing AI agents with structured workflows and tool permissions.",
    },
]


class GoogleSearchTool(ScriptTool[GoogleSearchInput, GoogleSearchOutput]):
    name = "google-search"
    description = "Search the web for pages matching a query"

    def execute(self, input: GoogleSearchInput) -> GoogleSearchOutput:
        query_lower = input.query.lower()
        matched = [r for r in _MOCK_RESULTS if any(w in r["title"].lower() or w in r["snippet"].lower() for w in query_lower.split())]
        if not matched:
            matched = _MOCK_RESULTS
        results = matched[: input.max_results]
        return GoogleSearchOutput(results=results, query=input.query, total_found=len(results))


if __name__ == "__main__":
    GoogleSearchTool.run()
