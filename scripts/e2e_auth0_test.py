"""E2E test for Auth0 integration.

Tests the full Auth0 flow against a real Auth0 tenant using M2M credentials.
Requires `.env.auth0` with valid Auth0 configuration.

This test does NOT use run_e2e.sh because it needs services started in auth0 mode.
Instead, use the dedicated runner:

    ./scripts/run_e2e_auth0.sh

Or manually:

    source .env.auth0
    docker compose up -d postgres
    NEOCORTEX_AUTH_MODE=auth0 NEOCORTEX_MOCK_DB=false uv run python -m neocortex &
    NEOCORTEX_AUTH_MODE=auth0 NEOCORTEX_MOCK_DB=false uv run python -m neocortex.ingestion &
    uv run python scripts/e2e_auth0_test.py
"""

from __future__ import annotations

import asyncio
import os
import sys
import uuid

import asyncpg
import httpx

from neocortex.config import PostgresConfig

INGESTION_BASE_URL = os.environ.get("NEOCORTEX_INGESTION_BASE_URL", "http://127.0.0.1:8001")
MCP_BASE_URL = os.environ.get("NEOCORTEX_BASE_URL", "http://127.0.0.1:8000")

# Auth0 config — must be set via .env.auth0
AUTH0_DOMAIN = os.environ.get("NEOCORTEX_AUTH0_DOMAIN", "")
AUTH0_AUDIENCE = os.environ.get("NEOCORTEX_AUTH0_AUDIENCE", "")
AUTH0_M2M_CLIENT_ID = os.environ.get("NEOCORTEX_AUTH0_M2M_CLIENT_ID", "")
AUTH0_M2M_CLIENT_SECRET = os.environ.get("NEOCORTEX_AUTH0_M2M_CLIENT_SECRET", "")

passed = 0
failed = 0


def report(status: str, message: str) -> None:
    global passed, failed
    if status == "PASS":
        passed += 1
    else:
        failed += 1
    print(f"  [{status}] {message}")


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _quote_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


async def get_m2m_token() -> str:
    """Get an M2M access token from Auth0 using client credentials grant."""
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            f"https://{AUTH0_DOMAIN}/oauth/token",
            json={
                "client_id": AUTH0_M2M_CLIENT_ID,
                "client_secret": AUTH0_M2M_CLIENT_SECRET,
                "audience": AUTH0_AUDIENCE,
                "grant_type": "client_credentials",
            },
        )
    resp.raise_for_status()
    data = resp.json()
    token = data.get("access_token")
    if not token:
        raise AssertionError(f"No access_token in Auth0 response: {data}")
    return token


async def test_health() -> None:
    """Verify both services are healthy."""
    print("Checking service health...")
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(f"{INGESTION_BASE_URL}/health")
        resp.raise_for_status()
        assert resp.json().get("status") == "ok"
        report("PASS", "Ingestion API healthy")

        resp = await client.get(f"{MCP_BASE_URL}/health")
        resp.raise_for_status()
        assert resp.json().get("status") == "ok"
        report("PASS", "MCP server healthy")


async def test_m2m_token_acquisition() -> str:
    """Get M2M token from Auth0 and verify it contains expected claims."""
    print("Acquiring M2M token from Auth0...")
    token = await get_m2m_token()

    # Decode without verification just to inspect claims
    import jwt as pyjwt

    claims = pyjwt.decode(token, options={"verify_signature": False})
    sub = claims.get("sub", "")
    aud = claims.get("aud", "")
    report("PASS", f"M2M token acquired (sub={sub[:30]}...)")

    if AUTH0_AUDIENCE in (aud if isinstance(aud, list) else [aud]):
        report("PASS", f"Token audience matches: {AUTH0_AUDIENCE}")
    else:
        report("FAIL", f"Token audience mismatch: expected {AUTH0_AUDIENCE}, got {aud}")

    return token


async def test_auth_rejection() -> None:
    """Verify that requests without valid Auth0 JWT are rejected."""
    print("Verifying auth rejection...")
    async with httpx.AsyncClient(base_url=INGESTION_BASE_URL, timeout=10.0) as client:
        # No token
        resp = await client.post("/ingest/text", json={"text": "should fail"})
        if resp.status_code == 401:
            report("PASS", "No token -> 401")
        else:
            report("FAIL", f"No token -> expected 401, got {resp.status_code}")

        # Invalid token
        resp = await client.post(
            "/ingest/text",
            json={"text": "should fail"},
            headers=_headers("not-a-valid-jwt-at-all"),
        )
        if resp.status_code == 401:
            report("PASS", "Invalid token -> 401")
        else:
            report("FAIL", f"Invalid token -> expected 401, got {resp.status_code}")

        # Expired/tampered token (valid JWT format but wrong signature)
        fake_jwt = "eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiJmYWtlIn0.invalid_signature"
        resp = await client.post(
            "/ingest/text",
            json={"text": "should fail"},
            headers=_headers(fake_jwt),
        )
        if resp.status_code == 401:
            report("PASS", "Tampered JWT -> 401")
        else:
            report("FAIL", f"Tampered JWT -> expected 401, got {resp.status_code}")


async def test_ingestion_with_auth0_token(token: str) -> str:
    """Ingest text using a real Auth0 M2M token and verify it's stored."""
    print("Ingesting text with Auth0 M2M token...")
    suffix = uuid.uuid4().hex[:8]
    text = f"auth0 e2e test memory {suffix}"

    async with httpx.AsyncClient(base_url=INGESTION_BASE_URL, timeout=10.0) as client:
        resp = await client.post(
            "/ingest/text",
            headers=_headers(token),
            json={"text": text},
        )

    if resp.status_code == 200:
        data = resp.json()
        if data.get("status") == "stored" and data.get("episodes_created") == 1:
            report("PASS", "Text ingested successfully (episode in response)")
        else:
            report("FAIL", f"Unexpected response body: {data}")
    else:
        report("FAIL", f"Ingestion failed: {resp.status_code} {resp.text}")

    return text


async def test_auto_provisioning(token: str) -> None:
    """Verify that the M2M client was auto-provisioned into the agent registry."""
    print("Verifying auto-provisioning in agent registry...")

    # Decode sub from the token
    import jwt as pyjwt

    claims = pyjwt.decode(token, options={"verify_signature": False})
    expected_sub = claims.get("sub", "")

    conn = await asyncpg.connect(dsn=PostgresConfig().dsn)
    try:
        row = await conn.fetchrow(
            "SELECT agent_id, is_admin FROM public.agent_registry WHERE agent_id = $1",
            expected_sub,
        )
        if row is not None:
            report("PASS", f"Agent auto-provisioned: {row['agent_id']}")
            if not row["is_admin"]:
                report("PASS", "M2M agent is not admin (correct — no admin:manage scope)")
            else:
                report("FAIL", "M2M agent should not be admin")
        else:
            report("FAIL", f"Agent not found in registry: {expected_sub}")
    finally:
        await conn.close()


async def test_data_in_db(token: str, text: str) -> None:
    """Verify the ingested text landed in the correct personal schema."""
    print("Verifying data in PostgreSQL...")

    # Auth0 M2M sub format: "clientid@clients" — schema uses sanitized agent_id
    # The schema name is ncx_{sanitized_agent_id}__personal
    # Find it by querying the episode table across schemas
    conn = await asyncpg.connect(dsn=PostgresConfig().dsn)
    try:
        # Find schemas that match the agent
        schemas = await conn.fetch(
            "SELECT schema_name FROM information_schema.schemata WHERE schema_name LIKE 'ncx_%__personal'"
        )
        found = False
        for row in schemas:
            schema = row["schema_name"]
            table = f"{_quote_identifier(schema)}.episode"
            try:
                ep = await conn.fetchrow(f"SELECT content FROM {table} WHERE content = $1", text)
                if ep is not None:
                    report("PASS", f"Episode found in schema: {schema}")
                    found = True
                    break
            except Exception:
                continue

        if not found:
            report("FAIL", f"Episode with text '{text[:40]}...' not found in any personal schema")
    finally:
        await conn.close()


async def test_mcp_oidc_discovery() -> None:
    """Verify the MCP server serves OAuth authorization server metadata."""
    print("Checking MCP server OAuth discovery...")

    # FastMCP serves RFC 8414 metadata; try common paths
    discovery_paths = [
        "/.well-known/oauth-authorization-server",
        "/.well-known/oauth-authorization-server/mcp",
        "/.well-known/openid-configuration",
    ]

    async with httpx.AsyncClient(timeout=10.0) as client:
        for path in discovery_paths:
            resp = await client.get(f"{MCP_BASE_URL}{path}")
            if resp.status_code == 200:
                data = resp.json()
                if "authorization_endpoint" in data or "issuer" in data:
                    report("PASS", f"OAuth discovery metadata served at {path}")
                    return
                else:
                    report("FAIL", f"Discovery at {path} returned 200 but missing expected fields: {list(data.keys())}")
                    return

    # None of the paths returned 200 — report the status codes for debugging
    codes = []
    async with httpx.AsyncClient(timeout=10.0) as client:
        for path in discovery_paths:
            resp = await client.get(f"{MCP_BASE_URL}{path}")
            codes.append(f"{path}={resp.status_code}")
    report("FAIL", f"OAuth discovery not found at any path: {', '.join(codes)}")


async def main() -> None:
    # Preflight: check Auth0 env vars
    missing = []
    for var in [
        "NEOCORTEX_AUTH0_DOMAIN",
        "NEOCORTEX_AUTH0_AUDIENCE",
        "NEOCORTEX_AUTH0_M2M_CLIENT_ID",
        "NEOCORTEX_AUTH0_M2M_CLIENT_SECRET",
    ]:
        if not os.environ.get(var):
            missing.append(var)
    if missing:
        print(f"ERROR: Missing required env vars: {', '.join(missing)}")
        print("Source .env.auth0 before running this test.")
        sys.exit(1)

    await test_health()
    token = await test_m2m_token_acquisition()
    await test_auth_rejection()
    text = await test_ingestion_with_auth0_token(token)
    await test_auto_provisioning(token)
    await test_data_in_db(token, text)
    await test_mcp_oidc_discovery()

    print(f"\nRESULTS: {passed} passed, {failed} failed")
    if failed > 0:
        sys.exit(1)
    print("ALL CHECKS PASSED")


if __name__ == "__main__":
    asyncio.run(main())
