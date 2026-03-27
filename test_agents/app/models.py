"""Pydantic models for test agents FastAPI request/response schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ContextMessage(BaseModel):
    """A single message in a conversation history."""

    role: str = Field(default="user", description="Message role: user | assistant | system")
    content: str = Field(description="Message content")


class AgentRunRequest(BaseModel):
    """Request body for running an agent."""

    prompt: str = Field(description="The user prompt / message to send to the agent")
    session_id: str = Field(default="", description="Resume an existing session (optional)")
    callback_url: str | None = Field(default=None, description="URL to POST full session result when agent completes")
    context: list[ContextMessage] | None = Field(default=None, description="Prepopulated conversation history")


class AgentRunResponse(BaseModel):
    """Response from an agent run."""

    session_id: str
    agent_name: str
    status: str  # "pending" | "running" | "completed" | "failed"
    output: str = ""
    error: str = ""


class CallbackPayload(BaseModel):
    """Payload POSTed to callback_url when an agent run finishes."""

    session_id: str
    agent_name: str
    status: str
    output: str = ""
    error: str = ""
    full_context: list[ContextMessage] = Field(default_factory=list)


class AgentInfo(BaseModel):
    """Metadata about an available agent."""

    name: str
    description: str
    mode: str  # "primary" or "subagent"
    model: str


class AgentListResponse(BaseModel):
    """Response listing all available agents."""

    agents: list[AgentInfo]


class SessionStatusResponse(BaseModel):
    """Response for checking a session's status."""

    session_id: str
    agent_name: str
    status: str
    output: str = ""
    error: str = ""
