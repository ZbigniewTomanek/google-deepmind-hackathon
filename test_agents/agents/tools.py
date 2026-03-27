"""Tool definitions shared across agents."""

from __future__ import annotations

from pathlib import Path

from open_agent_compiler.builders import ToolBuilder

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "agent_scripts"


def build_joke_tool():
    return (
        ToolBuilder()
        .name("joke-tool")
        .description("Generate a joke on a given topic and style")
        .from_script(str(SCRIPTS_DIR / "joke_tool.py"))
        .build()
    )


def build_youtube_search():
    return (
        ToolBuilder()
        .name("youtube-search-tool")
        .description("Search YouTube for videos matching a query")
        .from_script(str(SCRIPTS_DIR / "youtube_search.py"))
        .build()
    )


def build_google_search():
    return (
        ToolBuilder()
        .name("google-search-tool")
        .description("Search the web for pages matching a query")
        .from_script(str(SCRIPTS_DIR / "google_search.py"))
        .build()
    )


def build_task_manager():
    return (
        ToolBuilder()
        .name("task-manager")
        .description("Manage a todo list: add, list, complete, or delete tasks")
        .from_script(str(SCRIPTS_DIR / "task_manager.py"))
        .build()
    )
