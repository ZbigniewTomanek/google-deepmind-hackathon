"""Joke subagent definition."""

from __future__ import annotations

from open_agent_compiler.builders import AgentBuilder, WorkflowStepBuilder

from agents.tools import build_joke_tool


def build_joke_subagent(config):
    joke_tool = build_joke_tool()

    step = (
        WorkflowStepBuilder()
        .id("1")
        .name("Generate Joke")
        .todo("Generate joke", "Create a joke using the joke tool")
        .use_tool("joke-tool")
        .instructions("Use the joke-tool with the requested topic and style.")
        .mark_done("Generate joke")
        .build()
    )

    return (
        AgentBuilder()
        .name("joke-subagent")
        .description("Tells funny jokes on any topic")
        .mode("subagent")
        .config(config)
        .tool(joke_tool)
        .preamble("# Joke Subagent\n\nGenerate a funny joke using the joke-tool. Present it clearly.")
        .workflow_step(step)
        .temperature(0.7)
        .build()
    )
