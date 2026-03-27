"""Search orchestrator subagent definition."""

from __future__ import annotations

from open_agent_compiler.builders import AgentBuilder, WorkflowStepBuilder

from agents.tools import build_google_search, build_youtube_search


def build_search_orchestrator(config):
    yt_tool = build_youtube_search()
    google_tool = build_google_search()

    step = (
        WorkflowStepBuilder()
        .id("1")
        .name("Search")
        .todo("Search", "Search YouTube and/or Google")
        .use_tool("youtube-search-tool")
        .use_tool("google-search-tool")
        .instructions(
            "Use the appropriate search tool based on the query:\n"
            "- youtube-search-tool: for videos\n"
            "- google-search-tool: for articles/docs\n"
            "- Both if the user would benefit from mixed results."
        )
        .mark_done("Search")
        .build()
    )

    return (
        AgentBuilder()
        .name("search-orchestrator")
        .description("Searches YouTube and Google for information")
        .mode("subagent")
        .config(config)
        .tool(yt_tool)
        .tool(google_tool)
        .preamble("# Search Orchestrator\n\nSearch YouTube and Google. Present results clearly.")
        .workflow_step(step)
        .temperature(0.3)
        .build()
    )
