#!/usr/bin/env python3
"""YouTube search tool (mock implementation)."""

from pydantic import BaseModel, Field

from open_agent_compiler.runtime import ScriptTool


class YouTubeSearchInput(BaseModel):
    query: str = Field(description="Search query for YouTube")
    max_results: int = Field(default=5, description="Maximum number of results to return")


class YouTubeSearchOutput(BaseModel):
    results: list[dict]
    query: str
    total_found: int


_MOCK_RESULTS = [
    {
        "title": "Python 3.13 - What's New and Exciting",
        "channel": "TechTalks",
        "views": "125K",
        "url": "https://youtube.com/watch?v=mock1",
        "duration": "15:30",
    },
    {
        "title": "Building AI Agents with LangChain",
        "channel": "AI Engineering",
        "views": "89K",
        "url": "https://youtube.com/watch?v=mock2",
        "duration": "22:45",
    },
    {
        "title": "FastAPI Complete Tutorial 2026",
        "channel": "CodeAcademy",
        "views": "210K",
        "url": "https://youtube.com/watch?v=mock3",
        "duration": "45:00",
    },
    {
        "title": "Understanding MCP Servers for AI",
        "channel": "Anthropic Dev",
        "views": "45K",
        "url": "https://youtube.com/watch?v=mock4",
        "duration": "18:20",
    },
    {
        "title": "PostgreSQL Knowledge Graphs Tutorial",
        "channel": "DBMasters",
        "views": "67K",
        "url": "https://youtube.com/watch?v=mock5",
        "duration": "32:10",
    },
    {
        "title": "OpenCode Agent Framework Deep Dive",
        "channel": "Agent Builders",
        "views": "33K",
        "url": "https://youtube.com/watch?v=mock6",
        "duration": "28:15",
    },
]


class YouTubeSearchTool(ScriptTool[YouTubeSearchInput, YouTubeSearchOutput]):
    name = "youtube-search"
    description = "Search YouTube for videos matching a query"

    def execute(self, input: YouTubeSearchInput) -> YouTubeSearchOutput:
        # Mock: filter results by keyword presence in title
        query_lower = input.query.lower()
        matched = [r for r in _MOCK_RESULTS if any(w in r["title"].lower() for w in query_lower.split())]
        if not matched:
            matched = _MOCK_RESULTS  # fallback to all results
        results = matched[: input.max_results]
        return YouTubeSearchOutput(results=results, query=input.query, total_found=len(results))


if __name__ == "__main__":
    YouTubeSearchTool.run()
