import json

import pytest

from neocortex.auth.dev import DevTokenAuth
from neocortex.mcp_settings import MCPSettings


@pytest.mark.asyncio
async def test_multi_token_from_file(tmp_path) -> None:
    tokens_file = tmp_path / "dev_tokens.json"
    tokens_file.write_text(json.dumps({"alice-token": "alice", "bob-token": "bob"}))
    auth = DevTokenAuth(MCPSettings(auth_mode="dev_token", dev_tokens_file=str(tokens_file)))

    alice_token = await auth.verify_token("alice-token")
    bob_token = await auth.verify_token("bob-token")

    assert alice_token is not None
    assert alice_token.claims["sub"] == "alice"
    assert bob_token is not None
    assert bob_token.claims["sub"] == "bob"


@pytest.mark.asyncio
async def test_unknown_token_rejected(tmp_path) -> None:
    tokens_file = tmp_path / "dev_tokens.json"
    tokens_file.write_text(json.dumps({"alice-token": "alice"}))
    auth = DevTokenAuth(MCPSettings(auth_mode="dev_token", dev_tokens_file=str(tokens_file)))

    assert await auth.verify_token("unknown-token") is None


@pytest.mark.asyncio
async def test_fallback_single_token_when_file_missing() -> None:
    auth = DevTokenAuth(
        MCPSettings(
            auth_mode="dev_token",
            dev_token="legacy-token",
            dev_user_id="legacy-user",
            dev_tokens_file="/tmp/does-not-exist.json",
        )
    )

    token = await auth.verify_token("legacy-token")

    assert token is not None
    assert token.claims["sub"] == "legacy-user"
