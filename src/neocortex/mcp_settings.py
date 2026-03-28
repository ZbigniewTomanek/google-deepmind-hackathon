from typing import Literal

from pydantic_ai.settings import ThinkingLevel
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

    # Embedding model (experimental names may rotate)
    embedding_model: str = "gemini-embedding-001"

    # Hybrid recall weights (normalized at scoring time, so any ratio works)
    recall_weight_vector: float = 0.3
    recall_weight_text: float = 0.2
    recall_weight_recency: float = 0.1
    recall_recency_half_life_hours: float = 168.0  # 7 days
    # Vector distance threshold: cosine distance below this counts as a match.
    # 0.5 distance = 0.5 similarity. Tune up for stricter matching, down for broader.
    recall_vector_distance_threshold: float = 0.5

    # Cognitive heuristic weights (wired in Stage 2+)
    recall_weight_activation: float = 0.25
    recall_weight_importance: float = 0.15

    # ACT-R activation parameters
    activation_decay_rate: float = 0.5

    # Spreading activation
    spreading_activation_decay: float = 0.6
    spreading_activation_max_depth: int = 2

    # Soft-forget thresholds
    forget_activation_threshold: float = 0.05
    forget_importance_floor: float = 0.3

    # Edge reinforcement
    edge_reinforcement_delta: float = 0.05
    edge_weight_floor: float = 0.1
    edge_weight_ceiling: float = 2.0

    # Graph traversal
    recall_traversal_depth: int = 2  # hops from matched node

    # Extraction pipeline
    extraction_enabled: bool = True
    # Per-agent inference config (env: NEOCORTEX_<AGENT>_MODEL / _THINKING_EFFORT)
    # Thinking effort: minimal|low|medium|high|xhigh (maps to token budgets)
    ontology_model: str = "gemini-3-flash-preview"
    ontology_thinking_effort: ThinkingLevel = "low"
    extractor_model: str = "gemini-3-flash-preview"
    extractor_thinking_effort: ThinkingLevel = "low"
    librarian_model: str = "gemini-3-flash-preview"
    librarian_thinking_effort: ThinkingLevel = "low"

    # Admin
    bootstrap_admin_id: str = "admin"  # Seeded into agent_registry as admin on startup
    admin_token: str = "admin-token-neocortex"  # Bootstrap admin dev token

    # Feature flags
    mock_db: bool = True  # Use in-memory mock until PG is wired
