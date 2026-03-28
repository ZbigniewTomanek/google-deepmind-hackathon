"""CLI utility for ingesting the medical seed corpus into NeoCortex.

Usage:
    uv run python -m neocortex.extraction.cli --ingest-corpus
    uv run python -m neocortex.extraction.cli --ingest-corpus --base-url http://localhost:8001
    uv run python -m neocortex.extraction.cli --ingest-corpus --token alice-token
"""

from __future__ import annotations

import argparse
import asyncio
import sys

import httpx

from neocortex.extraction.corpus import MEDICAL_SEED_MESSAGES


async def ingest_seed_corpus(
    base_url: str = "http://localhost:8001",
    token: str | None = None,
) -> None:
    """POST each seed message to the /ingest/text endpoint."""
    headers: dict[str, str] = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    async with httpx.AsyncClient(base_url=base_url, headers=headers) as client:
        for i, msg in enumerate(MEDICAL_SEED_MESSAGES, 1):
            payload = {
                "text": msg["content"],
                "metadata": {
                    "id": msg["id"],
                    "title": msg["title"],
                    "topic": msg["topic"],
                },
            }
            resp = await client.post("/ingest/text", json=payload, timeout=30.0)
            if resp.status_code == 200:
                data = resp.json()
                print(f"  [{i}/{len(MEDICAL_SEED_MESSAGES)}] {msg['title']} — {data['status']}")
            else:
                print(
                    f"  [{i}/{len(MEDICAL_SEED_MESSAGES)}] {msg['title']} — "
                    f"FAILED ({resp.status_code}: {resp.text})",
                    file=sys.stderr,
                )

    print(f"\nDone. Ingested {len(MEDICAL_SEED_MESSAGES)} seed messages.")


def main() -> None:
    parser = argparse.ArgumentParser(description="NeoCortex extraction CLI utilities")
    parser.add_argument(
        "--ingest-corpus",
        action="store_true",
        help="Ingest the medical seed corpus via the ingestion API",
    )
    parser.add_argument(
        "--base-url",
        default="http://localhost:8001",
        help="Ingestion API base URL (default: http://localhost:8001)",
    )
    parser.add_argument(
        "--token",
        default=None,
        help="Bearer token for authentication",
    )
    args = parser.parse_args()

    if args.ingest_corpus:
        print(f"Ingesting seed corpus to {args.base_url}...")
        asyncio.run(ingest_seed_corpus(base_url=args.base_url, token=args.token))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
