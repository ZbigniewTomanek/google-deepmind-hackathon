"""Settings for the test agents FastAPI server."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    host: str = "0.0.0.0"
    port: int = 8003
    opencode_port: int = 4098

    # NeoCortex MCP server (the system under test)
    neocortex_mcp_url: str = "http://localhost:8000"
    neocortex_auth_token: str = "claude-code-work"

    # LLM provider
    zai_api_key: str = ""
    zai_base_url: str = "https://api.z.ai/api/coding/paas/v4"

    # Resolved paths
    project_root: str = str(Path(__file__).resolve().parent.parent)

    model_config = {"env_file": ".env", "extra": "ignore"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
