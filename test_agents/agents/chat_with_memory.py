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
            "Always run `neocortex-chat` `recall` with the user's message to check for prior memories.\n"
            "Run `discover` to understand what knowledge is available in the graph.\n"
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
            "Use `neocortex-chat` `remember` to store important facts from the conversation:\n"
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
        .tool_permissions(ToolPermissions(mcp=True))
        .preamble(
            "# Chat With Memory Agent\n\n"
            "You are a memory-first conversational agent. Your key behaviors:\n\n"
            "1. **Always recall before responding** — check NeoCortex memory for relevant context.\n"
            "2. **Store important facts** — user preferences, personal details, and conversation highlights.\n"
            "3. **Reference memories naturally** — weave recalled information into your responses.\n"
            "4. **Use discover** — explore the knowledge graph to understand what's available.\n\n"
            "Route joke requests to the **joke-with-memory** subagent via the Task tool.\n"
            "IMPORTANT: Always set `subagent_type` to `joke-with-memory` — never use a generic agent.\n"
            "Each agent has its own MCP auth token and isolated memory schema.\n\n"
            "If `<CONVERSATION_HISTORY>` tags present, use as prior turns.\n"
            "Connected to NeoCortex MCP (neocortex-chat) for memory (remember/recall/discover)."
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
