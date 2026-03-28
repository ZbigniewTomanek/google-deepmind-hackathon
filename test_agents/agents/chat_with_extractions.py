"""Chat agent for querying shared research graph extractions."""

from __future__ import annotations

from open_agent_compiler._types import AgentPermissions
from open_agent_compiler.builders import AgentBuilder, WorkflowStepBuilder


def build_chat_with_extractions(config):
    step_1 = (
        WorkflowStepBuilder()
        .id("1")
        .name("Recall")
        .todo("Recall context", "Search shared and personal graphs for relevant knowledge")
        .instructions(
            "Call MCP tools DIRECTLY yourself:\n"
            "1. Call `neocortex-chat-extractions_recall` with the user's message as query\n"
            "2. Note all relevant recalled facts for use in later steps.\n\n"
            "The recall will search across the shared research graph (ncx_shared__research)\n"
            "containing all ingested research findings (video transcripts, audio transcripts,\n"
            "RSS articles) as well as your personal memory graph."
        )
        .mark_done("Recall context")
        .build()
    )

    step_2 = (
        WorkflowStepBuilder()
        .id("2")
        .name("Discover")
        .todo("Discover structure", "Explore knowledge graph structure")
        .instructions(
            "Call `neocortex-chat-extractions_discover` to explore what knowledge is available.\n"
            "This helps you understand the structure and breadth of the research data.\n"
            "Use this to find additional relevant nodes and relationships not surfaced by recall."
        )
        .mark_done("Discover structure")
        .build()
    )

    step_3 = (
        WorkflowStepBuilder()
        .id("3")
        .name("Respond")
        .todo("Answer user", "Respond using recalled knowledge")
        .instructions(
            "Answer the user's question using the recalled and discovered knowledge.\n"
            "Reference specific findings naturally — cite sources (video titles, audio files,\n"
            "RSS articles) when available.\n"
            "If the knowledge graph doesn't contain relevant information, say so honestly."
        )
        .mark_done("Answer user")
        .build()
    )

    step_4 = (
        WorkflowStepBuilder()
        .id("4")
        .name("Remember")
        .todo("Store insights", "Store conversation insights in personal memory")
        .instructions(
            "Call `neocortex-chat-extractions_remember` DIRECTLY to store important insights:\n"
            "- Key conclusions drawn from combining multiple sources\n"
            "- User questions and interests (helps future recall relevance)\n"
            "- Connections between research findings not previously captured\n"
            "Do NOT store trivial or redundant information."
        )
        .mark_done("Store insights")
        .build()
    )

    return (
        AgentBuilder()
        .name("chat-with-extractions")
        .description("Query and discuss all research findings from the shared knowledge graph")
        .mode("primary")
        .config(config)
        .preamble(
            "# Chat With Extractions Agent\n\n"
            "You are a research assistant with access to all findings from the shared\n"
            "research graph (`ncx_shared__research`). This graph contains extracted\n"
            "knowledge from video transcripts, audio transcripts, and RSS feeds\n"
            "processed by the research pipeline.\n\n"
            "## CRITICAL RULES\n\n"
            "1. **Call MCP tools DIRECTLY yourself** — use `neocortex-chat-extractions_recall`,\n"
            "   `neocortex-chat-extractions_remember`, `neocortex-chat-extractions_discover`\n"
            "   directly. NEVER delegate MCP calls to a subagent.\n"
            "2. **Always recall before responding** — search the shared graph first.\n"
            "3. **Cite sources** — reference video titles, audio files, or RSS articles\n"
            "   when presenting findings.\n\n"
            "## Behaviors\n\n"
            "- **Recall first** — always search the shared research graph before answering.\n"
            "- **Discover to explore** — use discover to find graph structure and relationships.\n"
            "- **Synthesize across sources** — combine findings from different media types.\n"
            "- **Store insights** — remember key conclusions and user interests.\n\n"
            "If `<CONVERSATION_HISTORY>` tags present, use as prior turns.\n"
            "Connected to NeoCortex MCP (neocortex-chat-extractions) for shared research memory."
        )
        .workflow_step(step_1)
        .workflow_step(step_2)
        .workflow_step(step_3)
        .workflow_step(step_4)
        .permissions(AgentPermissions(
            extra=(("neocortex-chat-extractions*", "allow"),),
        ))
        .temperature(0.4)
        .steps(100)
        .color("#FF6B35")
        .build()
    )
