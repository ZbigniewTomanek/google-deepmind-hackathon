"""Agent runner — invokes compiled OpenCode agents via subprocess.

Extends the EcommerceAgent pattern with:
- Context injection: prepopulated conversation history injected into prompt
- Callback mechanism: POST full session result to a callback URL on completion
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from app.models import CallbackPayload, ContextMessage

logger = logging.getLogger(__name__)

# In Docker, build/ is mounted at /app. Locally, it's at test_agents/build.
_APP_DIR = Path("/app")
BUILD_DIR = _APP_DIR if _APP_DIR.exists() and (_APP_DIR / "opencode.json").exists() else Path(__file__).resolve().parent.parent / "build"

# In-memory session store
_sessions: dict[str, SessionState] = {}


@dataclass
class SessionState:
    session_id: str
    agent_name: str
    status: str = "pending"  # pending, running, completed, failed
    output: str = ""
    error: str = ""
    process: asyncio.subprocess.Process | None = field(default=None, repr=False)


def _agents_dir() -> Path:
    return BUILD_DIR / ".opencode" / "agents"


def _build_prompt_with_context(prompt: str, context: list[ContextMessage] | None) -> str:
    """Inject conversation history into the prompt.

    Wraps context in <CONVERSATION_HISTORY> tags so the chat agent's preamble
    knows to treat them as prior turns.
    """
    if not context:
        return prompt
    lines = ["<CONVERSATION_HISTORY>"]
    for msg in context:
        lines.append(f"[{msg.role.upper()}]: {msg.content}")
    lines.append("</CONVERSATION_HISTORY>")
    lines.append("")
    lines.append(f"Current request: {prompt}")
    return "\n".join(lines)


async def _fire_callback(callback_url: str, payload: CallbackPayload) -> None:
    """POST the full session result to the callback URL. Fire-and-forget."""
    try:
        import httpx

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(callback_url, json=payload.model_dump())
            logger.info("Callback to %s: %s", callback_url, response.status_code)
    except Exception as e:
        logger.error("Callback to %s failed: %s", callback_url, e)


def list_agents() -> list[dict[str, str]]:
    """List all compiled agents from the build directory."""
    agents_dir = _agents_dir()
    if not agents_dir.exists():
        return []

    agents = []
    for md_file in sorted(agents_dir.rglob("*.md")):
        content = md_file.read_text()
        if not content.startswith("---"):
            continue

        end = content.index("---", 3)
        frontmatter = content[3:end].strip()

        info: dict[str, str] = {"name": md_file.stem}
        for line in frontmatter.splitlines():
            line = line.strip()
            if line.startswith("description:"):
                info["description"] = line.split(":", 1)[1].strip()
            elif line.startswith("mode:"):
                info["mode"] = line.split(":", 1)[1].strip()
            elif line.startswith("model:"):
                info["model"] = line.split(":", 1)[1].strip()

        info.setdefault("description", "")
        info.setdefault("mode", "primary")
        info.setdefault("model", "")
        agents.append(info)

    return agents


def get_session(session_id: str) -> SessionState | None:
    """Retrieve session state by ID."""
    return _sessions.get(session_id)


def _resolve_agent(agent_name: str) -> tuple[str, str | None]:
    """Resolve agent name to agent ref. Returns (agent_ref, error)."""
    agents_dir = _agents_dir()
    agent_file = agents_dir / f"{agent_name}.md"
    if agent_file.exists():
        return agent_name, None
    matches = list(agents_dir.rglob(f"{agent_name}.md"))
    if matches:
        rel = matches[0].relative_to(agents_dir)
        return str(rel.with_suffix("")), None
    return "", f"Agent '{agent_name}' not found in {agents_dir}"


async def _run_subprocess(session: SessionState, agent_ref: str, full_prompt: str, callback_url: str | None, context: list[ContextMessage] | None) -> None:
    """Run the opencode subprocess and update session state."""
    opencode_url = f"http://localhost:{os.environ.get('OPENCODE_PORT', '4098')}"
    cmd = ["opencode", "run", "--attach", opencode_url, "--agent", agent_ref, full_prompt]

    proc = None
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(BUILD_DIR),
        )
        session.process = proc

        stdout_bytes, stderr_bytes = await asyncio.wait_for(proc.communicate(), timeout=300)
        stdout_text = stdout_bytes.decode("utf-8", errors="replace") if stdout_bytes else ""
        stderr_text = stderr_bytes.decode("utf-8", errors="replace") if stderr_bytes else ""

        if proc.returncode == 0:
            session.status = "completed"
            session.output = stdout_text
        else:
            session.status = "failed"
            session.output = stdout_text
            session.error = stderr_text or f"Process exited with code {proc.returncode}"

    except TimeoutError:
        session.status = "failed"
        session.error = "Agent execution timed out (300s limit)"
        if proc:
            proc.kill()

    except FileNotFoundError:
        session.status = "failed"
        session.error = (
            "opencode CLI not found. Install it or ensure it's in PATH. "
            "Falling back to direct tool execution."
        )
        session.output = await _fallback_direct_run(session.agent_name, full_prompt)
        if session.output:
            session.status = "completed"
            session.error = ""

    except Exception as e:
        session.status = "failed"
        session.error = str(e)

    # Fire callback if provided
    if callback_url:
        result_context = list(context or [])
        result_context.append(ContextMessage(role="user", content=full_prompt))
        if session.output:
            result_context.append(ContextMessage(role="assistant", content=session.output))

        asyncio.create_task(
            _fire_callback(
                callback_url,
                CallbackPayload(
                    session_id=session.session_id,
                    agent_name=session.agent_name,
                    status=session.status,
                    output=session.output,
                    error=session.error,
                    full_context=result_context,
                ),
            )
        )


async def start_agent(
    agent_name: str,
    prompt: str,
    session_id: str = "",
    callback_url: str | None = None,
    context: list[ContextMessage] | None = None,
) -> SessionState:
    """Start an agent in the background. Returns immediately with status=running."""
    if not session_id:
        session_id = f"sess-{uuid.uuid4().hex[:12]}"

    session = SessionState(session_id=session_id, agent_name=agent_name, status="running")
    _sessions[session_id] = session

    full_prompt = _build_prompt_with_context(prompt, context)
    agent_ref, error = _resolve_agent(agent_name)
    if error:
        session.status = "failed"
        session.error = error
        return session

    asyncio.create_task(_run_subprocess(session, agent_ref, full_prompt, callback_url, context))
    return session


async def run_agent(
    agent_name: str,
    prompt: str,
    session_id: str = "",
    callback_url: str | None = None,
    context: list[ContextMessage] | None = None,
) -> SessionState:
    """Run an agent synchronously — waits for completion before returning."""
    if not session_id:
        session_id = f"sess-{uuid.uuid4().hex[:12]}"

    session = SessionState(session_id=session_id, agent_name=agent_name, status="running")
    _sessions[session_id] = session

    full_prompt = _build_prompt_with_context(prompt, context)
    agent_ref, error = _resolve_agent(agent_name)
    if error:
        session.status = "failed"
        session.error = error
        return session

    await _run_subprocess(session, agent_ref, full_prompt, callback_url, context)
    return session


async def _fallback_direct_run(agent_name: str, prompt: str) -> str:
    """Fallback: run agent tools directly when opencode CLI is not available."""
    scripts_dir = BUILD_DIR / "scripts"

    if "joke" in agent_name or "joke" in prompt.lower():
        cmd = ["uv", "run", str(scripts_dir / "joke_tool.py"), "--topic", "programming"]
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(BUILD_DIR),
            )
            stdout, _ = await proc.communicate()
            if stdout:
                data = json.loads(stdout.decode())
                return f"Here's a joke about {data.get('topic', 'programming')}:\n\n{data.get('joke', 'No joke found')}"
        except Exception:
            pass

    if "search" in prompt.lower() or "find" in prompt.lower():
        tool = "youtube_search.py" if "youtube" in prompt.lower() or "video" in prompt.lower() else "google_search.py"
        cmd = ["uv", "run", str(scripts_dir / tool), "--query", prompt, "--max_results", "3"]
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(BUILD_DIR),
            )
            stdout, _ = await proc.communicate()
            if stdout:
                data = json.loads(stdout.decode())
                results = data.get("results", [])
                lines = [f"Found {data.get('total_found', 0)} results for: {data.get('query', prompt)}\n"]
                for r in results:
                    lines.append(f"  - {r.get('title', 'Untitled')} ({r.get('url', '')})")
                return "\n".join(lines)
        except Exception:
            pass

    return f"Agent '{agent_name}' acknowledged prompt: {prompt}\n(Full execution requires opencode CLI)"
