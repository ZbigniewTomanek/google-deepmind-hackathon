"""Tests for Auth0 integration configuration and components."""

from __future__ import annotations

from typing import cast
from unittest.mock import MagicMock, patch

import jwt.exceptions
import pytest

from neocortex.auth import create_auth
from neocortex.auth.auth0 import create_auth0_auth
from neocortex.auth.provisioning import _provisioned_cache, ensure_agent_provisioned
from neocortex.ingestion.auth0_jwt import Auth0JWTVerifier
from neocortex.mcp_settings import MCPSettings
from neocortex.permissions.memory_service import InMemoryPermissionService
from neocortex.permissions.protocol import PermissionChecker

# --- MCPSettings ---


def test_settings_accept_auth0_mode() -> None:
    s = MCPSettings(
        auth_mode="auth0",
        auth0_domain="test.auth0.com",
        auth0_audience="https://test",
        auth0_client_id="cid",
        auth0_client_secret="csecret",
    )
    assert s.auth_mode == "auth0"
    assert s.auth0_domain == "test.auth0.com"
    assert s.auth0_audience == "https://test"
    assert s.auth0_client_id == "cid"
    assert s.auth0_client_secret == "csecret"


def test_settings_default_auth0_fields_are_empty() -> None:
    s = MCPSettings(auth_mode="none")
    assert s.auth0_domain == ""
    assert s.auth0_client_id == ""
    assert s.auth0_client_secret == ""
    assert s.auth0_audience == ""
    assert s.auth0_m2m_client_id == ""
    assert s.auth0_m2m_client_secret == ""


def test_settings_none_mode_still_works() -> None:
    s = MCPSettings(auth_mode="none")
    assert s.auth_mode == "none"


def test_settings_dev_token_mode_still_works() -> None:
    s = MCPSettings(auth_mode="dev_token")
    assert s.auth_mode == "dev_token"


# --- create_auth() ---


def test_create_auth_returns_none_for_none_mode() -> None:
    s = MCPSettings(auth_mode="none")
    assert create_auth(s) is None


def test_create_auth_returns_auth0_provider() -> None:
    from fastmcp.server.auth.providers.auth0 import Auth0Provider

    oidc_response = MagicMock()
    oidc_response.status_code = 200
    oidc_response.raise_for_status = MagicMock()
    oidc_response.json.return_value = {
        "issuer": "https://test.auth0.com/",
        "authorization_endpoint": "https://test.auth0.com/authorize",
        "token_endpoint": "https://test.auth0.com/oauth/token",
        "jwks_uri": "https://test.auth0.com/.well-known/jwks.json",
        "response_types_supported": ["code"],
        "subject_types_supported": ["public"],
        "id_token_signing_alg_values_supported": ["RS256"],
    }

    s = MCPSettings(
        auth_mode="auth0",
        auth0_domain="test.auth0.com",
        auth0_client_id="cid",
        auth0_client_secret="csecret",
        auth0_audience="https://test-api",
    )
    with patch("httpx.get", return_value=oidc_response):
        auth = create_auth(s)
    assert isinstance(auth, Auth0Provider)


def test_create_auth0_auth_raises_without_domain() -> None:
    s = MCPSettings(auth_mode="auth0", auth0_domain="")
    with pytest.raises(ValueError, match="AUTH0_DOMAIN"):
        create_auth0_auth(s)


def test_create_auth0_auth_raises_without_client_id() -> None:
    s = MCPSettings(auth_mode="auth0", auth0_domain="test.auth0.com", auth0_client_id="")
    with pytest.raises(ValueError, match="AUTH0_CLIENT_ID"):
        create_auth0_auth(s)


def test_create_auth0_auth_raises_without_client_secret() -> None:
    s = MCPSettings(
        auth_mode="auth0",
        auth0_domain="test.auth0.com",
        auth0_client_id="cid",
        auth0_client_secret="",
    )
    with pytest.raises(ValueError, match="AUTH0_CLIENT_SECRET"):
        create_auth0_auth(s)


def test_create_auth0_auth_raises_without_audience() -> None:
    s = MCPSettings(
        auth_mode="auth0",
        auth0_domain="test.auth0.com",
        auth0_client_id="cid",
        auth0_client_secret="csecret",
        auth0_audience="",
    )
    with pytest.raises(ValueError, match="AUTH0_AUDIENCE"):
        create_auth0_auth(s)


# --- Auth0JWTVerifier ---


def test_jwt_verifier_rejects_invalid_token() -> None:
    verifier = Auth0JWTVerifier(domain="test.auth0.com", audience="https://test-api")
    with pytest.raises((jwt.exceptions.DecodeError, jwt.exceptions.PyJWTError)):
        verifier.verify("not-a-valid-jwt")


def test_jwt_verifier_sets_correct_issuer() -> None:
    verifier = Auth0JWTVerifier(domain="my-tenant.us.auth0.com", audience="https://api")
    assert verifier._issuer == "https://my-tenant.us.auth0.com/"


def test_jwt_verifier_sets_correct_jwks_uri() -> None:
    verifier = Auth0JWTVerifier(domain="my-tenant.us.auth0.com", audience="https://api")
    assert verifier._jwks_uri == "https://my-tenant.us.auth0.com/.well-known/jwks.json"


# --- ensure_agent_provisioned ---


@pytest.fixture(autouse=True)
def _clear_provisioning_cache():
    """Clear the module-level provisioning cache between tests."""
    _provisioned_cache.clear()
    yield
    _provisioned_cache.clear()


@pytest.mark.asyncio
async def test_provisioning_registers_new_agent() -> None:
    permissions = InMemoryPermissionService(bootstrap_admin_id="bootstrap")
    await ensure_agent_provisioned(
        permissions=permissions,
        agent_id="auth0|user123",
        auth0_permissions=["memory:read", "memory:write"],
    )
    agents = await permissions.list_agents()
    agent_ids = {a.agent_id for a in agents}
    assert "auth0|user123" in agent_ids

    # Should not be admin (no admin:manage permission)
    assert not await permissions.is_admin("auth0|user123")


@pytest.mark.asyncio
async def test_provisioning_promotes_admin() -> None:
    permissions = InMemoryPermissionService(bootstrap_admin_id="bootstrap")
    await ensure_agent_provisioned(
        permissions=permissions,
        agent_id="auth0|admin456",
        auth0_permissions=["memory:read", "memory:write", "admin:manage"],
    )
    assert await permissions.is_admin("auth0|admin456")


@pytest.mark.asyncio
async def test_provisioning_skips_existing_agent() -> None:
    permissions = InMemoryPermissionService(bootstrap_admin_id="bootstrap")
    # Pre-register agent
    await permissions.set_admin("auth0|existing", is_admin=False)

    # Provisioning with admin perms should NOT upgrade existing agent
    await ensure_agent_provisioned(
        permissions=permissions,
        agent_id="auth0|existing",
        auth0_permissions=["admin:manage"],
    )
    # Still not admin because provisioning skips already-registered agents
    assert not await permissions.is_admin("auth0|existing")


@pytest.mark.asyncio
async def test_provisioning_without_permissions() -> None:
    permissions = InMemoryPermissionService(bootstrap_admin_id="bootstrap")
    await ensure_agent_provisioned(
        permissions=permissions,
        agent_id="m2m-client@clients",
        auth0_permissions=None,
    )
    agents = await permissions.list_agents()
    agent_ids = {a.agent_id for a in agents}
    assert "m2m-client@clients" in agent_ids
    assert not await permissions.is_admin("m2m-client@clients")


@pytest.mark.asyncio
async def test_provisioning_cache_avoids_repeated_db_calls() -> None:
    permissions = InMemoryPermissionService(bootstrap_admin_id="bootstrap")
    await ensure_agent_provisioned(
        permissions=permissions,
        agent_id="auth0|cached",
        auth0_permissions=["memory:read"],
    )
    assert "auth0|cached" in _provisioned_cache

    # Second call should hit cache and skip list_agents entirely.
    # Passing a broken permissions object proves the DB is never touched.
    sentinel = cast(PermissionChecker, object())
    await ensure_agent_provisioned(
        permissions=sentinel,
        agent_id="auth0|cached",
    )
