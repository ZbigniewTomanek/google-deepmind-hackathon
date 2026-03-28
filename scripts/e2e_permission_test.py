"""E2E smoke test for the permission system.

Prerequisites:
  docker compose up -d postgres
  NEOCORTEX_AUTH_MODE=dev_token NEOCORTEX_DEV_TOKENS_FILE=dev_tokens.json \
    NEOCORTEX_MOCK_DB=false uv run python -m neocortex
  NEOCORTEX_AUTH_MODE=dev_token NEOCORTEX_DEV_TOKENS_FILE=dev_tokens.json \
    NEOCORTEX_MOCK_DB=false uv run python -m neocortex.ingestion

Usage:
  uv run python scripts/e2e_permission_test.py
"""

from __future__ import annotations

import asyncio
import os
import uuid

import asyncpg
import httpx

from neocortex.config import PostgresConfig

INGESTION_BASE_URL = os.environ.get("NEOCORTEX_INGESTION_BASE_URL", "http://127.0.0.1:8001")
ADMIN_TOKEN = os.environ.get("NEOCORTEX_ADMIN_TOKEN", "admin-token-neocortex")
ALICE_TOKEN = os.environ.get("NEOCORTEX_ALICE_TOKEN", "alice-token")
BOB_TOKEN = os.environ.get("NEOCORTEX_BOB_TOKEN", "bob-token")
EVE_TOKEN = os.environ.get("NEOCORTEX_EVE_TOKEN", "eve-token")


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _admin_request(method: str, path: str, token: str = ADMIN_TOKEN, **kwargs) -> httpx.Response:
    async with httpx.AsyncClient(base_url=INGESTION_BASE_URL, timeout=10.0) as client:
        return await client.request(method, path, headers=_headers(token), **kwargs)


async def _ingest_text(token: str, text: str, target_graph: str | None = None) -> httpx.Response:
    body: dict = {"text": text}
    if target_graph:
        body["target_graph"] = target_graph
    async with httpx.AsyncClient(base_url=INGESTION_BASE_URL, timeout=10.0) as client:
        return await client.post("/ingest/text", headers=_headers(token), json=body)


async def _assert_health() -> None:
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(f"{INGESTION_BASE_URL}/health")
    response.raise_for_status()
    payload = response.json()
    if payload.get("status") != "ok":
        raise AssertionError(f"Unexpected health payload: {payload}")


async def main() -> None:
    suffix = uuid.uuid4().hex[:8]
    purpose = f"e2e_perm_{suffix}"
    alice_text = f"alice shared knowledge {suffix}"
    bob_text = f"bob attempted write {suffix}"
    eve_text = f"eve unauthorized write {suffix}"

    # --- Health check ---
    print("Checking ingestion API health...")
    await _assert_health()

    # --- Step 1: Admin creates shared graph and grants permissions ---
    print("\nStep 1: Admin creates shared graph and grants permissions...")

    resp = await _admin_request("POST", "/admin/graphs", json={"purpose": purpose})
    assert resp.status_code == 200, f"Create graph failed: {resp.status_code} {resp.text}"
    schema_name = resp.json()["schema_name"]
    print(f"  Created graph: {schema_name}")

    # Grant alice read+write
    resp = await _admin_request(
        "POST",
        "/admin/permissions",
        json={
            "agent_id": "alice",
            "schema_name": schema_name,
            "can_read": True,
            "can_write": True,
        },
    )
    assert resp.status_code == 200, f"Grant alice failed: {resp.status_code} {resp.text}"
    print("  Granted alice read+write")

    # Grant bob read-only
    resp = await _admin_request(
        "POST",
        "/admin/permissions",
        json={
            "agent_id": "bob",
            "schema_name": schema_name,
            "can_read": True,
            "can_write": False,
        },
    )
    assert resp.status_code == 200, f"Grant bob failed: {resp.status_code} {resp.text}"
    print("  Granted bob read-only")

    # --- Step 2: Alice writes to shared graph (should succeed) ---
    print("\nStep 2: Alice ingests text to shared graph...")
    resp = await _ingest_text(ALICE_TOKEN, alice_text, target_graph=schema_name)
    assert resp.status_code == 200, f"Alice write failed: {resp.status_code} {resp.text}"
    result = resp.json()
    assert result["status"] == "stored" and result["episodes_created"] == 1, result
    print("  Alice write succeeded")

    # --- Step 3: Bob (read-only) denied write ---
    print("\nStep 3: Bob denied write to shared graph...")
    resp = await _ingest_text(BOB_TOKEN, bob_text, target_graph=schema_name)
    assert resp.status_code == 403, f"Expected 403 for Bob, got {resp.status_code}: {resp.text}"
    print("  Bob write correctly denied (403)")

    # --- Step 4: Eve (no permissions) denied write ---
    print("\nStep 4: Eve (unauthorized) denied write...")
    resp = await _ingest_text(EVE_TOKEN, eve_text, target_graph=schema_name)
    assert resp.status_code == 403, f"Expected 403 for Eve, got {resp.status_code}: {resp.text}"
    print("  Eve write correctly denied (403)")

    # --- Step 5: Read access verification via admin API ---
    print("\nStep 5: Verify read/write permissions via admin API...")

    # Alice has read+write
    resp = await _admin_request("GET", "/admin/permissions/alice")
    assert resp.status_code == 200
    alice_perms = resp.json()
    alice_perm = next((p for p in alice_perms if p["schema_name"] == schema_name), None)
    assert (
        alice_perm is not None and alice_perm["can_read"] and alice_perm["can_write"]
    ), f"Alice should have read+write: {alice_perms}"
    print("  Alice has read+write confirmed")

    # Bob has read-only
    resp = await _admin_request("GET", "/admin/permissions/bob")
    assert resp.status_code == 200
    bob_perms = resp.json()
    bob_perm = next((p for p in bob_perms if p["schema_name"] == schema_name), None)
    assert (
        bob_perm is not None and bob_perm["can_read"] and not bob_perm["can_write"]
    ), f"Bob should have read-only: {bob_perms}"
    print("  Bob has read-only confirmed")

    # Eve has no permissions
    resp = await _admin_request("GET", "/admin/permissions/eve")
    assert resp.status_code == 200
    eve_perms = resp.json()
    assert not any(p["schema_name"] == schema_name for p in eve_perms), f"Eve should have no permissions: {eve_perms}"
    print("  Eve has no permissions confirmed")

    # --- Step 6: Revoke alice's write -> 403 ---
    print("\nStep 6: Revoke Alice's write, verify 403...")

    # Update to read-only (re-grant with can_write=False)
    resp = await _admin_request(
        "POST",
        "/admin/permissions",
        json={
            "agent_id": "alice",
            "schema_name": schema_name,
            "can_read": True,
            "can_write": False,
        },
    )
    assert resp.status_code == 200, f"Update permission failed: {resp.status_code} {resp.text}"

    resp = await _ingest_text(ALICE_TOKEN, f"alice after revoke {suffix}", target_graph=schema_name)
    assert resp.status_code == 403, f"Expected 403 for Alice after revoke, got {resp.status_code}"
    print("  Alice write correctly denied after write revocation")

    # --- Step 7: Admin lifecycle (promote/demote) ---
    print("\nStep 7: Admin lifecycle (promote/demote Bob)...")

    # Promote Bob to admin
    resp = await _admin_request("PUT", "/admin/agents/bob/admin", json={"is_admin": True})
    assert resp.status_code == 200, f"Promote Bob failed: {resp.status_code} {resp.text}"
    print("  Bob promoted to admin")

    # Bob can now access admin endpoints
    resp = await _admin_request("GET", "/admin/agents", token=BOB_TOKEN)
    assert resp.status_code == 200, f"Bob admin access failed: {resp.status_code}"
    print("  Bob can access admin endpoints")

    # Demote Bob
    resp = await _admin_request("DELETE", "/admin/agents/bob/admin")
    assert resp.status_code == 200, f"Demote Bob failed: {resp.status_code} {resp.text}"
    print("  Bob demoted from admin")

    # Bob should get 403 on admin endpoints now
    resp = await _admin_request("GET", "/admin/agents", token=BOB_TOKEN)
    assert resp.status_code == 403, f"Expected 403 for demoted Bob, got {resp.status_code}"
    print("  Bob correctly denied admin access (403)")

    # Verify bootstrap admin cannot be demoted
    resp = await _admin_request("DELETE", "/admin/agents/admin/admin")
    assert resp.status_code == 400, f"Expected 400 for bootstrap demotion, got {resp.status_code}"
    print("  Bootstrap admin demotion correctly blocked (400)")

    # --- Step 8: Cleanup — drop graph, verify cascade ---
    print("\nStep 8: Admin drops shared graph...")

    resp = await _admin_request("DELETE", f"/admin/graphs/{schema_name}")
    assert resp.status_code == 200, f"Drop graph failed: {resp.status_code} {resp.text}"

    # Verify permissions are cascade-deleted
    resp = await _admin_request("GET", "/admin/permissions/alice")
    alice_perms = resp.json()
    assert not any(
        p["schema_name"] == schema_name for p in alice_perms
    ), f"Alice permissions should be cascade-deleted: {alice_perms}"

    resp = await _admin_request("GET", "/admin/permissions/bob")
    bob_perms = resp.json()
    assert not any(
        p["schema_name"] == schema_name for p in bob_perms
    ), f"Bob permissions should be cascade-deleted: {bob_perms}"
    print("  Graph dropped, permissions cascade-deleted")

    # --- Database verification ---
    print("\nVerifying PostgreSQL state...")
    conn = await asyncpg.connect(dsn=PostgresConfig().dsn)
    try:
        # After drop, schema should no longer exist
        schema_exists = await conn.fetchval(
            "SELECT EXISTS(SELECT 1 FROM information_schema.schemata WHERE schema_name = $1)",
            schema_name,
        )
        assert not schema_exists, f"Schema {schema_name} should have been dropped"
        print("  Schema correctly dropped from PostgreSQL")

        # graph_permissions should have no rows for this schema
        perm_count = await conn.fetchval(
            "SELECT count(*) FROM graph_permissions WHERE schema_name = $1",
            schema_name,
        )
        assert perm_count == 0, f"Expected 0 permission rows, got {perm_count}"
        print("  Permission rows cascade-deleted from PostgreSQL")
    finally:
        await conn.close()

    print("\nALL PERMISSION E2E CHECKS PASSED")


if __name__ == "__main__":
    asyncio.run(main())
