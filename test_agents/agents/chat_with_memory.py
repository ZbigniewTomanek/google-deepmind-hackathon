"""Primary chat agent with per-agent memory isolation."""

from __future__ import annotations

from open_agent_compiler._types import AgentPermissions, ToolPermissions
from open_agent_compiler.builders import AgentBuilder, SubagentBuilder, WorkflowStepBuilder


def build_chat_with_memory(config):
    joke_mem_ref = (
        SubagentBuilder()
        .name("joke-with-memory")
        .description("Tells jokes, remembers preferences")
        .build()
    )

    step_1 = (
        WorkflowStepBuilder()
        .id("1")
        .name("Recall Context")
        .todo("Recall context", "Check memory for relevant prior knowledge")
        .instructions(
            "Call the MCP tools DIRECTLY yourself (do NOT delegate to any subagent):\n"
            "1. Call `neocortex-chat_recall` with the user's message as query\n"
            "2. Call `neocortex-chat_discover` to see what knowledge is available\n\n"
            "Note any relevant recalled facts for use in later steps."
        )
        .mark_done("Recall context")
        .build()
    )

    step_2 = (
        WorkflowStepBuilder()
        .id("2")
        .name("Analyze Intent")
        .todo("Analyze intent", "Determine what the user wants")
        .evaluate("intent", "What is the user trying to do?", "joke", "remember", "general")
        .instructions(
            "Determine intent: joke, remember, or general.\n"
            "- joke: user wants a joke or humor\n"
            "- remember: user explicitly asks to store a fact or preference\n"
            "- general: anything else (questions, conversation, etc.)\n"
            "If <CONVERSATION_HISTORY> tags are present, use them as context."
        )
        .route("intent", "joke", goto="3")
        .route("intent", "remember", goto="4")
        .route("intent", "general", goto="4")
        .mark_done("Analyze intent")
        .build()
    )

    step_3 = (
        WorkflowStepBuilder()
        .id("3")
        .name("Joke")
        .todo("Get joke", "Delegate to joke-with-memory subagent")
        .gate("intent", "joke")
        .subagent("joke-with-memory")
        .instructions(
            "CRITICAL: You MUST use the Task tool with `subagent_type` set to EXACTLY `joke-with-memory`.\n"
            "Do NOT use a generic/general subagent — joke-with-memory has its own MCP auth token\n"
            "and its own isolated memory. Using any other agent type will break memory isolation.\n\n"
            "Pass the user's joke topic or request as the `prompt` parameter."
        )
        .mark_done("Get joke")
        .build()
    )

    step_4 = (
        WorkflowStepBuilder()
        .id("4")
        .name("Respond & Remember")
        .todo("Respond and remember", "Answer the user and store important facts")
        .instructions(
            "Answer the user's question or acknowledge their request.\n"
            "Reference any recalled memories naturally in your response.\n"
            "Call `neocortex-chat_remember` DIRECTLY (not via subagent) to store important facts:\n"
            "- User preferences, personal details, or explicit requests to remember\n"
            "- Key decisions or conversation highlights worth retaining\n"
            "Do NOT store trivial or redundant information."
        )
        .mark_done("Respond and remember")
        .build()
    )

    return (
        AgentBuilder()
        .name("chat-with-memory")
        .description("Memory-first chat agent — recalls context, stores facts, routes jokes to joke-with-memory")
        .mode("primary")
        .config(config)
        .subagent(joke_mem_ref)
        .preamble(
            "# Chat With Memory Agent\n\n"
            "You are a memory-first conversational agent.\n\n"
            "## CRITICAL RULES\n\n"
            "1. **Call MCP tools DIRECTLY yourself** — use `neocortex-chat_recall`, "
            "`neocortex-chat_remember`, `neocortex-chat_discover` directly. "
            "NEVER delegate MCP calls to a subagent.\n"
            "2. **The ONLY subagent you may invoke is `joke-with-memory`** — all other "
            "subagent types are BLOCKED. Do not attempt to create general or ad-hoc subagents.\n"
            "3. When invoking joke-with-memory, use Task tool with `subagent_type` set to "
            "EXACTLY `joke-with-memory`.\n\n"
            "## Behaviors\n\n"
            "- **Always recall before responding** — call `neocortex-chat_recall` with the user's message.\n"
            "- **Store important facts** — call `neocortex-chat_remember` for user preferences and key facts.\n"
            "- **Reference memories naturally** — weave recalled information into responses.\n"
            "- **Use discover** — call `neocortex-chat_discover` to explore the knowledge graph.\n\n"
            "If `<CONVERSATION_HISTORY>` tags present, use as prior turns.\n"
            "Connected to NeoCortex MCP (neocortex-chat) for memory."
        )
        .workflow_step(step_1)
        .workflow_step(step_2)
        .workflow_step(step_3)
        .workflow_step(step_4)
        .permissions(AgentPermissions(
            extra=(("neocortex-chat*", "allow"),),
        ))
        .temperature(0.4)
        .steps(100)
        .color("#6B8E23")
        .build()
    )
