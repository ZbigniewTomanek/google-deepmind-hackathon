"""E2E test for audio/video media ingestion (real ffmpeg + real DB, Gemini mock).

Uploads the demo clip fixtures (MP3 + MP4) to the running ingestion server,
verifies the API response shape, checks that episodes were created in the
agent's schema, and confirms that compressed media files landed on disk.

Prerequisites (handled by run_e2e.sh):
  - PostgreSQL running via docker compose
  - Ingestion server on :8001 with dev_token auth

Usage:
  ./scripts/run_e2e.sh scripts/e2e_media_ingestion_test.py
"""

from __future__ import annotations

import asyncio
import os
import pathlib

import asyncpg
import httpx

from neocortex.config import PostgresConfig

BASE_URL = os.environ.get("NEOCORTEX_INGESTION_BASE_URL", "http://127.0.0.1:8001")
ALICE_TOKEN = os.environ.get("NEOCORTEX_ALICE_TOKEN", "alice-token")

FIXTURES_DIR = pathlib.Path(__file__).resolve().parent.parent / "tests" / "e2e" / "fixtures"

ALICE_SCHEMA = "ncx_alice__personal"


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _quote_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


async def _assert_health() -> None:
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(f"{BASE_URL}/health")
    resp.raise_for_status()
    assert resp.json().get("status") == "ok", f"Unexpected health: {resp.json()}"


async def _upload_media(
    path: str,
    endpoint: str,
    content_type: str,
    token: str,
    metadata: dict | None = None,
    target_graph: str | None = None,
) -> dict:
    """Upload a media file and return the JSON response."""
    filename = os.path.basename(path)
    with open(path, "rb") as f:
        data: dict[str, str] = {}
        if metadata is not None:
            import json

            data["metadata"] = json.dumps(metadata)
        if target_graph is not None:
            data["target_graph"] = target_graph

        async with httpx.AsyncClient(base_url=BASE_URL, timeout=120.0) as client:
            resp = await client.post(
                endpoint,
                headers=_headers(token),
                files={"file": (filename, f, content_type)},
                data=data,
            )
    if resp.status_code != 200:
        raise AssertionError(f"{endpoint} returned {resp.status_code}: {resp.text}")
    return resp.json()


async def _count_episodes_like(
    conn: asyncpg.Connection,
    schema_name: str,
    source_type: str,
    content_pattern: str,
) -> int:
    table = f"{_quote_identifier(schema_name)}.episode"
    row = await conn.fetchrow(
        f"SELECT count(*) AS cnt FROM {table} WHERE source_type = $1 AND content LIKE $2",
        source_type,
        content_pattern,
    )
    return row["cnt"] if row else 0


async def main() -> None:
    # Verify fixture files exist
    mp3_path = FIXTURES_DIR / "demo_clip.mp3"
    mp4_path = FIXTURES_DIR / "demo_clip.mp4"
    for p in (mp3_path, mp4_path):
        if not p.exists():
            raise FileNotFoundError(f"Fixture not found: {p}")

    print("=== E2E Media Ingestion Test ===\n")

    # --- Health ---
    print("[1/6] Health check...")
    await _assert_health()
    print("  PASS\n")

    # --- Upload audio (MP3) ---
    print("[2/6] Uploading audio (demo_clip.mp3)...")
    audio_result = await _upload_media(
        str(mp3_path),
        "/ingest/audio",
        "audio/mpeg",
        ALICE_TOKEN,
        metadata={"source": "e2e_test", "context": "DataWalk entity resolution demo"},
    )
    assert audio_result["status"] == "stored", f"Audio upload failed: {audio_result}"
    assert audio_result["episodes_created"] == 1, f"Expected 1 episode, got {audio_result}"
    assert audio_result.get("media_ref") is not None, "Missing media_ref in audio response"
    audio_ref = audio_result["media_ref"]
    assert audio_ref["original_filename"] == "demo_clip.mp3"
    assert audio_ref["content_type"] == "audio/mpeg"
    assert audio_ref["compressed_size"] > 0
    assert audio_ref.get("duration_seconds", 0) > 60, f"Expected >60s duration, got {audio_ref.get('duration_seconds')}"
    print(
        f"  Audio stored: {audio_ref['relative_path']} "
        f"({audio_ref['compressed_size']} bytes, {audio_ref['duration_seconds']:.1f}s)"
    )
    print("  PASS\n")

    # --- Upload video (MP4) ---
    print("[3/6] Uploading video (demo_clip.mp4)...")
    video_result = await _upload_media(
        str(mp4_path),
        "/ingest/video",
        "video/mp4",
        ALICE_TOKEN,
        metadata={"source": "e2e_test", "context": "DataWalk entity resolution demo"},
    )
    assert video_result["status"] == "stored", f"Video upload failed: {video_result}"
    assert video_result["episodes_created"] == 1, f"Expected 1 episode, got {video_result}"
    assert video_result.get("media_ref") is not None, "Missing media_ref in video response"
    video_ref = video_result["media_ref"]
    assert video_ref["original_filename"] == "demo_clip.mp4"
    assert video_ref["content_type"] == "video/mp4"
    assert video_ref["compressed_size"] > 0
    assert video_ref.get("duration_seconds", 0) > 60, f"Expected >60s duration, got {video_ref.get('duration_seconds')}"
    print(
        f"  Video stored: {video_ref['relative_path']} "
        f"({video_ref['compressed_size']} bytes, {video_ref['duration_seconds']:.1f}s)"
    )
    print("  PASS\n")

    # --- Verify media files on disk ---
    print("[4/6] Verifying compressed media files on disk...")
    media_store = os.environ.get("NEOCORTEX_MEDIA_STORE_PATH", "./media_store")
    audio_disk = os.path.join(media_store, audio_ref["relative_path"])
    video_disk = os.path.join(media_store, video_ref["relative_path"])
    assert os.path.isfile(audio_disk), f"Audio file missing on disk: {audio_disk}"
    assert os.path.isfile(video_disk), f"Video file missing on disk: {video_disk}"
    assert os.path.getsize(audio_disk) == audio_ref["compressed_size"]
    assert os.path.getsize(video_disk) == video_ref["compressed_size"]
    print(f"  Audio on disk: {audio_disk} ({os.path.getsize(audio_disk)} bytes)")
    print(f"  Video on disk: {video_disk} ({os.path.getsize(video_disk)} bytes)")
    print("  PASS\n")

    # --- Verify episodes in database ---
    print("[5/6] Verifying episodes in PostgreSQL...")
    conn = await asyncpg.connect(dsn=PostgresConfig().dsn)
    try:
        audio_count = await _count_episodes_like(conn, ALICE_SCHEMA, "ingestion_audio", "%demo_clip.mp3%")
        assert audio_count >= 1, f"No audio episode found in {ALICE_SCHEMA}"

        video_count = await _count_episodes_like(conn, ALICE_SCHEMA, "ingestion_video", "%demo_clip.mp4%")
        assert video_count >= 1, f"No video episode found in {ALICE_SCHEMA}"
        print(f"  Audio episodes: {audio_count}, Video episodes: {video_count}")
    finally:
        await conn.close()
    print("  PASS\n")

    # --- Verify rejection of unsupported types ---
    print("[6/6] Verifying content-type rejection...")
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as client:
        resp = await client.post(
            "/ingest/audio",
            headers=_headers(ALICE_TOKEN),
            files={"file": ("bad.txt", b"not audio", "text/plain")},
        )
    assert resp.status_code == 415, f"Expected 415, got {resp.status_code}"

    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as client:
        resp = await client.post(
            "/ingest/video",
            headers=_headers(ALICE_TOKEN),
            files={"file": ("bad.pdf", b"%PDF-fake", "application/pdf")},
        )
    assert resp.status_code == 415, f"Expected 415, got {resp.status_code}"
    print("  PASS\n")

    print("=== ALL MEDIA INGESTION CHECKS PASSED ===")


if __name__ == "__main__":
    asyncio.run(main())
