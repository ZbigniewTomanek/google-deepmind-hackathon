"""Primary chat agent definition."""

from __future__ import annotations

from open_agent_compiler._types import AgentPermissions
from open_agent_compiler.builders import AgentBuilder, SubagentBuilder, WorkflowStepBuilder


def build_chat(config):
    search_ref = SubagentBuilder().name("search-orchestrator").description("Searches YouTube and Google").build()
    task_ref = SubagentBuilder().name("task-subagent").description("Creates and manages todo lists").build()
    joke_ref = SubagentBuilder().name("joke-subagent").description("Tells funny jokes").build()

    step_1 = (
        WorkflowStepBuilder()
        .id("1")
        .name("Analyze Intent")
        .todo("Analyze intent", "Determine what the user wants")
        .evaluate("intent", "What is the user trying to do?", "search", "task", "joke", "general")
        .instructions(
            "Determine intent: search, task, joke, or general.\n"
            "If <CONVERSATION_HISTORY> tags are present, use them as context."
        )
        .route("intent", "search", goto="2")
        .route("intent", "task", goto="3")
        .route("intent", "joke", goto="4")
        .route("intent", "general", goto="5")
        .mark_done("Analyze intent")
        .build()
    )

    step_2 = (
        WorkflowStepBuilder()
        .id("2")
        .name("Search")
        .todo("Run search", "Delegate to search orchestrator")
        .gate("intent", "search")
        .subagent("search-orchestrator")
        .instructions("Invoke search-orchestrator with the user's query.")
        .mark_done("Run search")
        .build()
    )

    step_3 = (
        WorkflowStepBuilder()
        .id("3")
        .name("Task Management")
        .todo("Run task manager", "Delegate to task subagent")
        .gate("intent", "task")
        .subagent("task-subagent")
        .instructions("Invoke task-subagent with the user's request.")
        .mark_done("Run task manager")
        .build()
    )

    step_4 = (
        WorkflowStepBuilder()
        .id("4")
        .name("Tell Joke")
        .todo("Run joke agent", "Delegate to joke subagent")
        .gate("intent", "joke")
        .subagent("joke-subagent")
        .instructions("Invoke joke-subagent with the user's topic.")
        .mark_done("Run joke agent")
        .build()
    )

    step_5 = (
        WorkflowStepBuilder()
        .id("5")
        .name("General Response")
        .todo("Answer directly", "Respond to general conversation")
        .gate("intent", "general")
        .instructions(
            "Answer directly. Use NeoCortex MCP tools if relevant:\n"
            "- remember: Store facts\n"
            "- recall: Retrieve memories\n"
            "- discover: Explore knowledge graph"
        )
        .mark_done("Answer directly")
        .build()
    )

    return (
        AgentBuilder()
        .name("chat")
        .description("Primary chat agent — routes to search, task, and joke subagents")
        .mode("primary")
        .config(config)
        .subagent(search_ref)
        .subagent(task_ref)
        .subagent(joke_ref)
        .preamble(
            "# Chat Agent\n\n"
            "Route requests to subagents: search-orchestrator, task-subagent, joke-subagent.\n"
            "For general questions, answer directly.\n"
            "If `<CONVERSATION_HISTORY>` tags present, use as prior turns.\n"
            "Connected to NeoCortex MCP for memory (remember/recall/discover)."
        )
        .workflow_step(step_1)
        .workflow_step(step_2)
        .workflow_step(step_3)
        .workflow_step(step_4)
        .workflow_step(step_5)
        .permissions(AgentPermissions(doom_loop="deny"))
        .temperature(0.4)
        .steps(100)
        .color("#4A90D9")
        .build()
    )
