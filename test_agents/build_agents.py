"""Compile test agents into build/."""

from __future__ import annotations

import subprocess
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from open_agent_compiler.compiler import compile_agent
from open_agent_compiler.writers import OpenCodeWriter

from agents import (
    build_chat,
    build_chat_with_memory,
    build_joke_subagent,
    build_joke_with_memory,
    build_search_orchestrator,
    build_task_subagent,
)
from agents.config import build_config

BUILD_DIR = Path(__file__).resolve().parent / "build"
SCRIPTS_DIR = Path(__file__).resolve().parent / "agent_scripts"


_BUILD_PYPROJECT = """\
[project]
name = "neocortex-test-agents"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = ["pydantic>=2.0", "open-agent-compiler>=0.1.0"]
"""


def _ensure_build_scaffold(build_dir: Path) -> None:
    """Ensure build/ has pyproject.toml and git repo for opencode project detection."""
    build_dir.mkdir(parents=True, exist_ok=True)

    # Always write pyproject.toml so dependencies stay in sync
    (build_dir / "pyproject.toml").write_text(_BUILD_PYPROJECT)

    # Git repo marks build/ as a project root for opencode
    if not (build_dir / ".git").exists():
        subprocess.run(["git", "init"], cwd=build_dir, capture_output=True)
        (build_dir / ".gitignore").write_text("*\n")
        subprocess.run(["git", "add", "-f", ".gitignore"], cwd=build_dir, capture_output=True)
        subprocess.run(["git", "commit", "-m", "project marker"], cwd=build_dir, capture_output=True)


def compile_and_write() -> Path:
    config = build_config()

    agents = [
        build_chat(config),
        build_search_orchestrator(config),
        build_task_subagent(config),
        build_joke_subagent(config),
        build_chat_with_memory(config),
        build_joke_with_memory(config),
    ]

    writer = OpenCodeWriter(output_dir=BUILD_DIR, scripts_dir=SCRIPTS_DIR)
    for agent_def in agents:
        compiled = compile_agent(agent_def, target="opencode")
        writer.write(compiled)

    _ensure_build_scaffold(BUILD_DIR)

    return BUILD_DIR


def main() -> None:
    build_dir = compile_and_write()
    print(f"Agents compiled to {build_dir}")
    for md in sorted((build_dir / ".opencode" / "agents").glob("*.md")):
        print(f"  - {md.stem}")


if __name__ == "__main__":
    main()
