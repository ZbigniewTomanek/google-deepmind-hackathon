import json
from pathlib import Path

from neocortex.mcp_settings import MCPSettings


def load_token_map(settings: MCPSettings) -> dict[str, str]:
    """Load the token-to-agent-id mapping from settings.

    Reads from ``dev_tokens.json`` if configured, otherwise falls back
    to the single ``dev_token`` / ``dev_user_id`` pair.
    """
    token_map: dict[str, str] = {}

    if settings.dev_tokens_file:
        tokens_path = Path(settings.dev_tokens_file)
        if tokens_path.exists():
            raw_value = json.loads(tokens_path.read_text())
            if isinstance(raw_value, dict):
                token_map = {str(token): str(agent_id) for token, agent_id in raw_value.items()}

    if not token_map:
        token_map = {settings.dev_token: settings.dev_user_id}

    return token_map
