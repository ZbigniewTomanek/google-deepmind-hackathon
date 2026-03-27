"""Task subagent definition."""

from __future__ import annotations

from open_agent_compiler.builders import AgentBuilder, WorkflowStepBuilder

from agents.tools import build_task_manager


def build_task_subagent(config):
    task_tool = build_task_manager()

    step = (
        WorkflowStepBuilder()
        .id("1")
        .name("Manage Tasks")
        .todo("Manage tasks", "Execute the requested task operation")
        .use_tool("task-manager")
        .instructions(
            "Use task-manager with:\n"
            "- action=add, title=... : Create task\n"
            "- action=list : Show tasks\n"
            "- action=complete, task_id=... : Complete task\n"
            "- action=delete, task_id=... : Delete task"
        )
        .mark_done("Manage tasks")
        .build()
    )

    return (
        AgentBuilder()
        .name("task-subagent")
        .description("Creates and manages todo lists")
        .mode("subagent")
        .config(config)
        .tool(task_tool)
        .preamble("# Task Subagent\n\nManage todo lists. Show the updated list after changes.")
        .workflow_step(step)
        .temperature(0.2)
        .build()
    )
