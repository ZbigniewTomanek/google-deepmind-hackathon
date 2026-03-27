"""E2E smoke test for the ingestion API.

Prerequisites:
  docker compose up -d postgres
  NEOCORTEX_AUTH_MODE=dev_token NEOCORTEX_DEV_TOKENS_FILE=dev_tokens.json \
    NEOCORTEX_MOCK_DB=false uv run python -m neocortex.ingestion

Usage:
  uv run python scripts/e2e_ingestion_test.py
"""

from __future__ import annotations

import asyncio
import os
import uuid

import asyncpg
import httpx

from neocortex.config import PostgresConfig

BASE_URL = os.environ.get("NEOCORTEX_INGESTION_BASE_URL", "http://127.0.0.1:8001")
ALICE_TOKEN = os.environ.get("NEOCORTEX_ALICE_TOKEN", "alice-token")
BOB_TOKEN = os.environ.get("NEOCORTEX_BOB_TOKEN", "bob-token")


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _quote_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


async def _post(path: str, token: str, **kwargs) -> dict:
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as client:
        resp = await client.post(path, headers=_headers(token), **kwargs)
    resp.raise_for_status()
    return resp.json()


async def _assert_health() -> None:
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(f"{BASE_URL}/health")
    response.raise_for_status()
    payload = response.json()
    if payload.get("status") != "ok":
        raise AssertionError(f"Unexpected health payload: {payload}")


async def _assert_auth_rejected() -> None:
    """Verify that requests without a valid token are rejected."""
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as client:
        resp = await client.post("/ingest/text", json={"text": "should fail"})
    if resp.status_code != 401:
        raise AssertionError(f"Expected 401, got {resp.status_code}")

    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as client:
        resp = await client.post(
            "/ingest/text",
            json={"text": "should fail"},
            headers=_headers("bogus-token"),
        )
    if resp.status_code != 401:
        raise AssertionError(f"Expected 401 for invalid token, got {resp.status_code}")


async def _assert_episode_in_schema(
    conn: asyncpg.Connection,
    schema_name: str,
    expected_content: str,
    source_type: str,
) -> None:
    table = f"{_quote_identifier(schema_name)}.episode"
    row = await conn.fetchrow(
        f"SELECT content, source_type FROM {table} WHERE content = $1",
        expected_content,
    )
    if row is None:
        raise AssertionError(f"Episode not found in {schema_name}: {expected_content!r}")
    if row["source_type"] != source_type:
        raise AssertionError(f"Expected source_type={source_type!r}, got {row['source_type']!r}")


async def _assert_episode_absent(
    conn: asyncpg.Connection,
    schema_name: str,
    content: str,
) -> None:
    table = f"{_quote_identifier(schema_name)}.episode"
    row = await conn.fetchrow(
        f"SELECT 1 FROM {table} WHERE content = $1",
        content,
    )
    if row is not None:
        raise AssertionError(f"Content should not be in {schema_name}: {content!r}")


async def main() -> None:
    suffix = uuid.uuid4().hex[:8]
    alice_text = f"alice ingestion text {suffix}"
    bob_text = f"bob ingestion text {suffix}"
    alice_doc = f"alice doc content {suffix}"
    alice_event = {"type": "click", "marker": f"alice_event_{suffix}"}
    bob_event = {"type": "view", "marker": f"bob_event_{suffix}"}

    alice_schema = "ncx_alice__personal"
    bob_schema = "ncx_bob__personal"

    # --- Health ---
    print("Checking ingestion API health...")
    await _assert_health()

    # --- Auth ---
    print("Verifying auth rejection for missing/invalid tokens...")
    await _assert_auth_rejected()

    # --- Text ingestion ---
    print("Ingesting text for Alice...")
    result = await _post("/ingest/text", ALICE_TOKEN, json={"text": alice_text})
    assert result["status"] == "stored" and result["episodes_created"] == 1, result

    print("Ingesting text for Bob...")
    result = await _post("/ingest/text", BOB_TOKEN, json={"text": bob_text})
    assert result["status"] == "stored" and result["episodes_created"] == 1, result

    # --- Document upload ---
    print("Uploading document for Alice...")
    result = await _post(
        "/ingest/document",
        ALICE_TOKEN,
        files={"file": ("notes.md", alice_doc.encode(), "text/markdown")},
    )
    assert result["status"] == "stored" and result["episodes_created"] == 1, result

    # --- Events ingestion ---
    print("Ingesting events for Alice...")
    result = await _post(
        "/ingest/events",
        ALICE_TOKEN,
        json={"events": [alice_event]},
    )
    assert result["status"] == "stored" and result["episodes_created"] == 1, result

    print("Ingesting events for Bob...")
    result = await _post(
        "/ingest/events",
        BOB_TOKEN,
        json={"events": [bob_event]},
    )
    assert result["status"] == "stored" and result["episodes_created"] == 1, result

    # --- Content-type rejection ---
    print("Verifying unsupported content type rejected...")
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as client:
        resp = await client.post(
            "/ingest/document",
            headers=_headers(ALICE_TOKEN),
            files={"file": ("evil.exe", b"MZ", "application/octet-stream")},
        )
    if resp.status_code != 415:
        raise AssertionError(f"Expected 415, got {resp.status_code}")

    # --- Database verification ---
    print("Verifying PostgreSQL data isolation...")
    conn = await asyncpg.connect(dsn=PostgresConfig().dsn)
    try:
        import json as _json

        # Alice's text is in Alice's schema
        await _assert_episode_in_schema(conn, alice_schema, alice_text, "ingestion_text")
        # Bob's text is in Bob's schema
        await _assert_episode_in_schema(conn, bob_schema, bob_text, "ingestion_text")

        # Alice's document in Alice's schema
        await _assert_episode_in_schema(conn, alice_schema, alice_doc, "ingestion_document")

        # Alice's event in Alice's schema
        await _assert_episode_in_schema(conn, alice_schema, _json.dumps(alice_event), "ingestion_event")
        # Bob's event in Bob's schema
        await _assert_episode_in_schema(conn, bob_schema, _json.dumps(bob_event), "ingestion_event")

        # Cross-agent isolation: Alice's data not in Bob's schema
        await _assert_episode_absent(conn, bob_schema, alice_text)
        await _assert_episode_absent(conn, bob_schema, alice_doc)

        # Cross-agent isolation: Bob's data not in Alice's schema
        await _assert_episode_absent(conn, alice_schema, bob_text)
    finally:
        await conn.close()

    print("ALL CHECKS PASSED")


if __name__ == "__main__":
    asyncio.run(main())
