"""Compile test agents into build/."""

from __future__ import annotations

import subprocess
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from open_agent_compiler.compiler import compile_agent
from open_agent_compiler.writers import OpenCodeWriter

from agents import build_chat, build_joke_subagent, build_search_orchestrator, build_task_subagent
from agents.config import build_config

BUILD_DIR = Path(__file__).resolve().parent / "build"
SCRIPTS_DIR = Path(__file__).resolve().parent / "agent_scripts"


def _ensure_git_marker(build_dir: Path) -> None:
    """Ensure build/ has a git repo so opencode detects it as a project root."""
    if (build_dir / ".git").exists():
        return
    build_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init"], cwd=build_dir, capture_output=True)
    gitignore = build_dir / ".gitignore"
    gitignore.write_text("*\n")
    subprocess.run(["git", "add", "-f", ".gitignore"], cwd=build_dir, capture_output=True)
    subprocess.run(["git", "commit", "-m", "project marker"], cwd=build_dir, capture_output=True)


def compile_and_write() -> Path:
    config = build_config()

    agents = [
        build_chat(config),
        build_search_orchestrator(config),
        build_task_subagent(config),
        build_joke_subagent(config),
    ]

    writer = OpenCodeWriter(output_dir=BUILD_DIR, scripts_dir=SCRIPTS_DIR)
    for agent_def in agents:
        compiled = compile_agent(agent_def, target="opencode")
        writer.write(compiled)

    _ensure_git_marker(BUILD_DIR)

    return BUILD_DIR


def main() -> None:
    build_dir = compile_and_write()
    print(f"Agents compiled to {build_dir}")
    for md in sorted((build_dir / ".opencode" / "agents").glob("*.md")):
        print(f"  - {md.stem}")


if __name__ == "__main__":
    main()
