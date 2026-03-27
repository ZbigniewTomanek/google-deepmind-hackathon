"""Abstract transport protocol for benchmark adapters."""

from __future__ import annotations

from typing import Protocol

from benchmarks.models import IngestResult, SearchResult, Session


class MemoryProvider(Protocol):
    """Common interface for benchmark memory providers."""

    async def initialize(self) -> None:
        """Initialize any provider resources."""

    async def ingest_sessions(self, sessions: list[Session]) -> IngestResult:
        """Ingest normalized sessions into the provider."""

    async def await_indexing(self, result: IngestResult) -> None:
        """Wait for ingested data to become searchable."""

    async def search(self, query: str, limit: int = 10) -> list[SearchResult]:
        """Search for relevant memory results."""

    async def clear(self) -> None:
        """Clear provider state for an isolated benchmark run."""
