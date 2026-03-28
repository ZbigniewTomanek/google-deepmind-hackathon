"""Joke subagent with per-agent memory isolation."""

from __future__ import annotations

from open_agent_compiler._types import AgentPermissions, ToolPermissions
from open_agent_compiler.builders import AgentBuilder, WorkflowStepBuilder

from agents.tools import build_joke_tool


def build_joke_with_memory(config):
    joke_tool = build_joke_tool()

    step_1 = (
        WorkflowStepBuilder()
        .id("1")
        .name("Recall Preferences")
        .todo("Recall preferences", "Check memory for user's joke preferences")
        .instructions(
            "Run `neocortex-joke` `recall` to check for the user's joke preferences.\n"
            "Look for: favorite topics, preferred joke style (puns, one-liners, stories),\n"
            "topics they enjoyed or disliked in the past.\n"
            "Note any recalled preferences for use in the next step."
        )
        .mark_done("Recall preferences")
        .build()
    )

    step_2 = (
        WorkflowStepBuilder()
        .id("2")
        .name("Generate Joke")
        .todo("Generate joke", "Create a joke using the joke tool")
        .use_tool("joke-tool")
        .instructions(
            "Use the joke-tool with the requested topic and style.\n"
            "If preferences were recalled in step 1, apply them:\n"
            "- Use the user's preferred joke style if known\n"
            "- Favor topics they've enjoyed before\n"
            "- Avoid topics they've disliked\n"
            "Present the joke clearly."
        )
        .mark_done("Generate joke")
        .build()
    )

    step_3 = (
        WorkflowStepBuilder()
        .id("3")
        .name("Remember Feedback")
        .todo("Remember feedback", "Store joke topic and style for future personalization")
        .instructions(
            "Use `neocortex-joke` `remember` to store:\n"
            "- The joke topic that was requested\n"
            "- The style of joke that was generated\n"
            "- Any user feedback or reactions if available\n"
            "This helps personalize future jokes for this user."
        )
        .mark_done("Remember feedback")
        .build()
    )

    return (
        AgentBuilder()
        .name("joke-with-memory")
        .description("Tells jokes and remembers preferences for personalization")
        .mode("subagent")
        .config(config)
        .tool(joke_tool)
        .tool_permissions(ToolPermissions(mcp=True))
        .preamble(
            "# Joke With Memory Agent\n\n"
            "You are a joke-telling agent that remembers preferences across conversations.\n\n"
            "1. **Recall preferences** — check NeoCortex memory for joke preferences before generating.\n"
            "2. **Personalize jokes** — apply recalled preferences (topics, style) to the joke.\n"
            "3. **Remember for next time** — store the topic and style for future personalization.\n\n"
            "Connected to NeoCortex MCP (neocortex-joke) for memory (remember/recall/discover)."
        )
        .workflow_step(step_1)
        .workflow_step(step_2)
        .workflow_step(step_3)
        .permissions(AgentPermissions(
            extra=(("neocortex-joke*", "allow"),),
        ))
        .temperature(0.7)
        .build()
    )
