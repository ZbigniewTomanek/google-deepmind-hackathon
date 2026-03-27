from typing import Literal

from pydantic_settings import BaseSettings


class MCPSettings(BaseSettings):
    """MCP server configuration. Loaded from env vars with NEOCORTEX_ prefix."""

    model_config = {
        "env_prefix": "NEOCORTEX_",
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }

    # Server
    server_name: str = "NeoCortex"
    server_host: str = "127.0.0.1"
    server_port: int = 8000
    transport: Literal["stdio", "http", "sse", "streamable-http"] = "http"

    # Authentication — "none" | "dev_token" | "google_oauth"
    #  - none: no auth, all requests are anonymous
    #  - dev_token: static bearer token for testing (no browser flow needed)
    #  - google_oauth: full Google OAuth via FastMCP OAuthProxy
    auth_mode: Literal["none", "dev_token", "google_oauth"] = "none"

    # Dev-token auth (used when auth_mode = "dev_token")
    dev_token: str = "dev-token-neocortex"  # Deprecated single-token fallback
    dev_user_id: str = "dev-user"  # Deprecated single-user fallback
    dev_tokens_file: str = ""  # Optional JSON mapping {token: agent_id}

    # Google OAuth (used when auth_mode = "google_oauth")
    google_client_id: str = ""
    google_client_secret: str = ""
    oauth_base_url: str = "http://localhost:8000"

    # Embedding model (experimental names may rotate; fallback: "text-embedding-004")
    embedding_model: str = "gemini-embedding-exp-03-07"

    # Feature flags
    mock_db: bool = True  # Use in-memory mock until PG is wired
