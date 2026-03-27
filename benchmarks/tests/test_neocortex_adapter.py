from __future__ import annotations

import asyncio
import socket
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any

import httpx
import pytest
import uvicorn

from benchmarks.adapters.neocortex_adapter import (
    NeoCortexAdapter,
    NeoCortexConfig,
    question_scope_agent_id,
)
from benchmarks.models import MessageRole, Session, SessionMessage
from neocortex.db.mock import InMemoryRepository
from neocortex.ingestion.app import create_app
from neocortex.mcp_settings import MCPSettings
from neocortex.server import create_server
from neocortex.services import create_services, shutdown_services


class RecordingEmbeddingService:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def embed(self, text: str) -> list[float] | None:
        self.calls.append(text)
        return [0.5, 0.5]


class RecordingRepository(InMemoryRepository):
    def __init__(self) -> None:
        super().__init__()
        self.updated_embeddings: list[tuple[int, list[float], str]] = []
        self.recall_calls: list[dict[str, object]] = []

    async def recall(
        self, query: str, agent_id: str, limit: int = 10, query_embedding: list[float] | None = None
    ):
        self.recall_calls.append(
            {
                "query": query,
                "agent_id": agent_id,
                "limit": limit,
                "query_embedding": query_embedding,
            }
        )
        return await super().recall(query, agent_id, limit, query_embedding=query_embedding)

    async def update_episode_embedding(self, episode_id: int, embedding: list[float], agent_id: str) -> None:
        self.updated_embeddings.append((episode_id, embedding, agent_id))
        await super().update_episode_embedding(episode_id, embedding, agent_id)


def make_session(
    session_id: str,
    user_content: str,
    assistant_content: str,
    *,
    timestamp: datetime | None = None,
) -> Session:
    return Session(
        session_id=session_id,
        timestamp=timestamp,
        messages=[
            SessionMessage(role=MessageRole.USER, content=user_content),
            SessionMessage(role=MessageRole.ASSISTANT, content=assistant_content),
        ],
    )


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@asynccontextmanager
async def _serve_http_app(app: Any):
    port = _free_port()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    task = asyncio.create_task(server.serve())
    base_url = f"http://127.0.0.1:{port}"

    try:
        async with httpx.AsyncClient() as client:
            for _ in range(50):
                if task.done():
                    break
                try:
                    response = await client.get(f"{base_url}/health")
                except httpx.HTTPError:
                    await asyncio.sleep(0.1)
                    continue
                if response.status_code == 200:
                    break
                await asyncio.sleep(0.1)
            else:
                raise RuntimeError(f"Timed out waiting for test server at {base_url}")
        yield base_url
    finally:
        server.should_exit = True
        await task


@pytest.mark.asyncio
async def test_question_scope_agent_id_is_deterministic() -> None:
    first = question_scope_agent_id("run-1", "question-1")
    second = question_scope_agent_id("run-1", "question-1")
    third = question_scope_agent_id("run-1", "question-2")

    assert first == second
    assert third != first
    assert first.startswith("bench")
    assert first.isalnum()


@pytest.mark.asyncio
async def test_direct_adapter_mock_db_isolates_question_scopes() -> None:
    shared_context = await create_services(MCPSettings(auth_mode="none", mock_db=True))
    adapter_a = NeoCortexAdapter(
        NeoCortexConfig(run_id="bench-run", question_id="question-a", mock_db=True),
        service_context=shared_context,
    )
    adapter_b = NeoCortexAdapter(
        NeoCortexConfig(run_id="bench-run", question_id="question-b", mock_db=True),
        service_context=shared_context,
    )
    await adapter_a.initialize()
    await adapter_b.initialize()

    try:
        result_a = await adapter_a.ingest_sessions(
            [
                make_session(
                    "session-a",
                    "Alice likes oolong tea",
                    "The saved preference is oolong tea.",
                    timestamp=datetime(2026, 3, 27, 12, 0, 0),
                )
            ]
        )
        result_b = await adapter_b.ingest_sessions(
            [
                make_session(
                    "session-b",
                    "Bob prefers espresso",
                    "The saved preference is espresso.",
                    timestamp=datetime(2026, 3, 27, 12, 5, 0),
                )
            ]
        )

        assert result_a.sessions_ingested == 1
        assert result_b.sessions_ingested == 1

        search_a = await adapter_a.search("oolong")
        leak_a = await adapter_a.search("espresso")
        search_b = await adapter_b.search("espresso")

        assert len(search_a) == 1
        assert "oolong" in search_a[0].content.lower()
        assert leak_a == []
        assert len(search_b) == 1
        assert "espresso" in search_b[0].content.lower()
    finally:
        await shutdown_services(shared_context)


@pytest.mark.asyncio
async def test_direct_adapter_clear_only_removes_current_scope_from_shared_mock_repo() -> None:
    shared_context = await create_services(MCPSettings(auth_mode="none", mock_db=True))
    adapter_a = NeoCortexAdapter(
        NeoCortexConfig(run_id="bench-run", question_id="question-a", mock_db=True),
        service_context=shared_context,
    )
    adapter_b = NeoCortexAdapter(
        NeoCortexConfig(run_id="bench-run", question_id="question-b", mock_db=True),
        service_context=shared_context,
    )
    await adapter_a.initialize()
    await adapter_b.initialize()

    try:
        await adapter_a.ingest_sessions([make_session("session-a", "Alice likes tea", "oolong")])
        await adapter_b.ingest_sessions([make_session("session-b", "Bob likes coffee", "espresso")])

        await adapter_a.clear()

        assert await adapter_a.search("tea") == []
        remaining = await adapter_b.search("coffee")
        assert len(remaining) == 1
        assert "coffee" in remaining[0].content.lower()
    finally:
        await shutdown_services(shared_context)


@pytest.mark.asyncio
async def test_direct_adapter_uses_embeddings_for_ingest_and_recall() -> None:
    repo = RecordingRepository()
    embeddings = RecordingEmbeddingService()
    shared_context = {
        "repo": repo,
        "pg": None,
        "graph": None,
        "schema_mgr": None,
        "router": None,
        "settings": MCPSettings(auth_mode="none", mock_db=True),
        "embeddings": embeddings,
    }
    adapter = NeoCortexAdapter(
        NeoCortexConfig(run_id="embedding-run", question_id="question-1", mock_db=True),
        service_context=shared_context,
    )
    await adapter.initialize()

    ingest = await adapter.ingest_sessions([make_session("session-1", "Alice likes tea", "oolong")])
    results = await adapter.search("tea")

    assert ingest.sessions_ingested == 1
    assert len(results) == 1
    assert len(embeddings.calls) == 2
    assert "Alice likes tea" in embeddings.calls[0]
    assert embeddings.calls[1] == "tea"
    assert repo.updated_embeddings == [(ingest.episode_ids[0], [0.5, 0.5], adapter.agent_id)]
    assert repo.recall_calls == [
        {
            "query": "tea",
            "agent_id": adapter.agent_id,
            "limit": 10,
            "query_embedding": [0.5, 0.5],
        }
    ]


@pytest.mark.asyncio
async def test_mcp_transport_smoke_wires_real_streamable_http_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    shared_context = await create_services(MCPSettings(auth_mode="none", mock_db=True))

    async def shared_services(*_args: object, **_kwargs: object):
        return shared_context

    async def noop_shutdown(*_args: object, **_kwargs: object) -> None:
        return None

    monkeypatch.setattr("neocortex.server.create_services", shared_services)
    monkeypatch.setattr("neocortex.server.shutdown_services", noop_shutdown)

    mcp = create_server(MCPSettings(auth_mode="none", mock_db=True, transport="streamable-http"))
    async with _serve_http_app(mcp.http_app(path="/mcp", transport="streamable-http")) as mcp_base_url:
        adapter = NeoCortexAdapter(
            NeoCortexConfig(
                transport="mcp",
                run_id="smoke",
                question_id="question-mcp",
                mcp_base_url=mcp_base_url,
            )
        )
        session = make_session("session-mcp", "Alice likes oolong tea", "Stored through MCP transport")

        try:
            await adapter.initialize()
            ingest = await adapter.ingest_sessions([session])
            results = await adapter.search("oolong")
        finally:
            await adapter.close()
            await shutdown_services(shared_context)

    assert ingest.sessions_ingested == 1
    assert len(ingest.episode_ids) == 1
    assert ingest.errors == []
    assert len(results) == 1
    assert "oolong" in results[0].content.lower()


@pytest.mark.asyncio
async def test_rest_transport_smoke_parses_ingestion_response_and_recalls_via_mcp(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    shared_context = await create_services(MCPSettings(auth_mode="none", mock_db=True))

    async def shared_services(*_args: object, **_kwargs: object):
        return shared_context

    async def noop_shutdown(*_args: object, **_kwargs: object) -> None:
        return None

    monkeypatch.setattr("neocortex.server.create_services", shared_services)
    monkeypatch.setattr("neocortex.server.shutdown_services", noop_shutdown)
    monkeypatch.setattr("neocortex.ingestion.app.create_services", shared_services)
    monkeypatch.setattr("neocortex.ingestion.app.shutdown_services", noop_shutdown)

    mcp = create_server(MCPSettings(auth_mode="none", mock_db=True, transport="streamable-http"))
    ingestion_app = create_app(MCPSettings(auth_mode="none", mock_db=True))

    async with (
        _serve_http_app(mcp.http_app(path="/mcp", transport="streamable-http")) as mcp_base_url,
        _serve_http_app(ingestion_app) as rest_base_url,
    ):
        adapter = NeoCortexAdapter(
            NeoCortexConfig(
                transport="rest",
                run_id="smoke",
                question_id="question-rest",
                mcp_base_url=mcp_base_url,
                rest_base_url=rest_base_url,
            )
        )
        session = make_session("session-rest", "Bob prefers espresso", "Stored through REST transport")

        try:
            await adapter.initialize()
            ingest = await adapter.ingest_sessions([session])
            results = await adapter.search("espresso")
        finally:
            await adapter.close()
            await shutdown_services(shared_context)

    assert ingest.sessions_ingested == 1
    assert ingest.episode_ids == []
    assert ingest.errors == []
    assert len(results) == 1
    assert "espresso" in results[0].content.lower()
