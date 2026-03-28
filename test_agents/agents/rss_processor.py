"""RSS processor subagent — parses feeds and stores to shared research graph."""

from __future__ import annotations

from open_agent_compiler._types import AgentPermissions
from open_agent_compiler.builders import AgentBuilder, WorkflowStepBuilder

from agents.tools import build_list_input_files, build_parse_local_rss


def build_rss_processor(config):
    list_files_tool = build_list_input_files()
    rss_tool = build_parse_local_rss()

    step_1 = (
        WorkflowStepBuilder()
        .id("1")
        .name("Process RSS")
        .todo("Process RSS", "Parse local RSS feed file")
        .use_tool("parse-local-rss")
        .instructions(
            "Parse the local RSS/Atom feed file using parse-local-rss.\n"
            "Review the parsed items and identify key stories, trends, and notable content.\n"
            "Note the most important items and any emerging themes across entries."
        )
        .mark_done("Process RSS")
        .build()
    )

    step_2 = (
        WorkflowStepBuilder()
        .id("2")
        .name("Share Findings")
        .todo("Share findings", "Store parsed items and key findings to shared research graph")
        .instructions(
            "Store key findings in the shared research graph using `neocortex-rss-proc` `remember`.\n\n"
            "For each important item, call `remember` with:\n"
            "- `target_graph`: `ncx_shared__research`\n"
            "- `text`: the key content (story title, summary, key points)\n"
            "- `context`: source metadata (e.g., 'RSS feed: {feed_title}, item: {item_title}')\n\n"
            "Be selective — store stories with substantive content, not every feed item."
        )
        .mark_done("Share findings")
        .build()
    )

    return (
        AgentBuilder()
        .name("rss-processor")
        .description("Parses local RSS feeds and stores findings in shared research graph")
        .mode("subagent")
        .config(config)
        .tool(list_files_tool)
        .tool(rss_tool)
        .preamble(
            "# RSS Processor\n\n"
            "You are an RSS processing subagent that parses local feed files\n"
            "and stores structured findings in a shared research knowledge graph.\n\n"
            "## Your capabilities:\n"
            "- **RSS parsing**: Parse local RSS/Atom feed files into structured items\n"
            "- **Shared memory**: Store findings via NeoCortex MCP (neocortex-rss-proc)\n\n"
            "## Workflow:\n"
            "1. Parse the RSS feed file and identify key content\n"
            "2. Store important items and findings to the shared research graph\n\n"
            "All findings go to `ncx_shared__research` via `remember(target_graph=...)`.\n"
            "Connected to NeoCortex MCP (neocortex-rss-proc) for shared graph access."
        )
        .workflow_step(step_1)
        .workflow_step(step_2)
        .permissions(AgentPermissions(
            extra=(("neocortex-rss-proc*", "allow"),),
        ))
        .temperature(0.3)
        .build()
    )
