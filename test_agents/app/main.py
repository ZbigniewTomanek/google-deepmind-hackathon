"""FastAPI application — HTTP API for triggering test agents."""

from __future__ import annotations

import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException

# Ensure test_agents root is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.agent_runner import get_session, list_agents, run_agent, start_agent
from app.models import (
    AgentInfo,
    AgentListResponse,
    AgentRunRequest,
    AgentRunResponse,
    SessionStatusResponse,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Compile agents on startup if not already compiled."""
    build_dir = Path(__file__).resolve().parent.parent / "build"
    if not (build_dir / ".opencode" / "agents").exists():
        print("Agents not found — compiling...")
        from build_agents import compile_and_write

        compile_and_write()
        print("Agents compiled successfully.")
    else:
        print(f"Using existing agents at {build_dir / '.opencode' / 'agents'}")
    yield


app = FastAPI(
    title="NeoCortex Test Agents API",
    description=(
        "FastAPI service for triggering test AI agents built with "
        "OpenAgentCompiler. Tests NeoCortex memory capabilities via MCP."
    ),
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/agents", response_model=AgentListResponse)
async def get_agents():
    """List all available compiled agents."""
    raw = list_agents()
    agents = [
        AgentInfo(
            name=a["name"],
            description=a["description"],
            mode=a["mode"],
            model=a["model"],
        )
        for a in raw
    ]
    return AgentListResponse(agents=agents)


@app.post("/agents/{agent_name}/run", response_model=AgentRunResponse)
async def trigger_agent(agent_name: str, request: AgentRunRequest):
    """Run an agent with a prompt and optional context/callback.

    - **prompt**: The user's message
    - **session_id**: Resume an existing session (optional, auto-generated)
    - **async_mode**: If true, return immediately and poll /sessions/{id}
    - **callback_url**: URL to POST full session result on completion
    - **context**: Prepopulated conversation history (list of {role, content})
    """
    if request.async_mode:
        session = await start_agent(
            agent_name=agent_name,
            prompt=request.prompt,
            session_id=request.session_id,
            callback_url=request.callback_url,
            context=request.context,
        )
    else:
        session = await run_agent(
            agent_name=agent_name,
            prompt=request.prompt,
            session_id=request.session_id,
            callback_url=request.callback_url,
            context=request.context,
        )
    return AgentRunResponse(
        session_id=session.session_id,
        agent_name=session.agent_name,
        status=session.status,
        output=session.output,
        error=session.error,
    )


@app.get("/sessions/{session_id}", response_model=SessionStatusResponse)
async def get_session_status(session_id: str):
    """Check the status of an agent session."""
    session = get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")
    return SessionStatusResponse(
        session_id=session.session_id,
        agent_name=session.agent_name,
        status=session.status,
        output=session.output,
        error=session.error,
    )


@app.post("/agents/compile")
async def recompile_agents():
    """Force recompilation of all agents."""
    from build_agents import compile_and_write

    build_dir = compile_and_write()
    return {"message": "Agents recompiled", "build_dir": str(build_dir)}


@app.get("/health")
async def health():
    return {"status": "ok", "service": "neocortex-test-agents", "model": "zai-coding-plan/glm-5"}
