import re

_MAX_SUB_LENGTH = 46
_SAFE_CHARS = re.compile(r"[^a-z0-9_]")


def oauth_sub_to_pg_role(oauth_sub: str) -> str:
    """Map an OAuth subject claim to a PostgreSQL role name."""
    sanitized = _SAFE_CHARS.sub("_", oauth_sub.lower())[:_MAX_SUB_LENGTH]
    return f"neocortex_agent_{sanitized}"
