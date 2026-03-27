"""NeoCortex benchmark adapter.

Stage 1 uses `direct` for benchmark-scored LongMemEval runs.
The `mcp` and `rest` transports are smoke/integration paths only and do
not provide the per-question isolation guarantees required for scored runs.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
from typing import TYPE_CHECKING, Any, Literal

import httpx
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport
from pydantic import BaseModel, ConfigDict

from benchmarks.models import IngestResult, SearchResult, Session
from neocortex.db.mock import InMemoryRepository
from neocortex.ingestion.models import IngestionResult as RestIngestionResult
from neocortex.mcp_settings import MCPSettings
from neocortex.schemas.memory import RecallResult, RememberResult
from neocortex.services import ServiceContext, create_services, shutdown_services

if TYPE_CHECKING:
    from neocortex.db.protocol import MemoryRepository
    from neocortex.embedding_service import EmbeddingService

_NON_ALNUM_PATTERN = re.compile(r"[^a-z0-9]+")


def _scope_fragment(value: str, *, max_length: int) -> str:
    normalized = _NON_ALNUM_PATTERN.sub("", value.strip().lower())
    if normalized:
        return normalized[:max_length]
    return "x"


def question_scope_seed(run_id: str, question_id: str) -> str:
    """Return the stable raw scope seed for one benchmark question."""

    return f"{run_id}::{question_id}"


def question_scope_agent_id(run_id: str, question_id: str) -> str:
    """Return a deterministic NeoCortex agent identity for one question scope."""

    seed = question_scope_seed(run_id, question_id)
    digest = hashlib.sha1(seed.encode("utf-8")).hexdigest()[:12]
    run_fragment = _scope_fragment(run_id, max_length=6)
    question_fragment = _scope_fragment(question_id, max_length=6)
    return f"bench{run_fragment}{question_fragment}{digest}"


class NeoCortexConfig(BaseModel):
    """Configuration for the NeoCortex benchmark adapter."""

    model_config = ConfigDict(extra="forbid")

    transport: Literal["direct", "mcp", "rest"] = "direct"
    run_id: str
    question_id: str
    mock_db: bool = False
    mcp_base_url: str = "http://localhost:8000"
    rest_base_url: str = "http://localhost:8001"
    auth_token: str | None = None
    request_timeout_seconds: float = 60.0


class NeoCortexAdapter:
    """MemoryProvider-compatible adapter for benchmark runs."""

    def __init__(
        self,
        config: NeoCortexConfig,
        *,
        service_context: ServiceContext | None = None,
    ) -> None:
        self._config = config
        self._service_context = service_context
        self._owns_service_context = service_context is None
        self._mcp_client: Client | None = None
        self._http_client: httpx.AsyncClient | None = None

    @property
    def agent_id(self) -> str:
        """Return the effective identity for this adapter.

        Only the direct transport gets a deterministic per-question agent ID.
        Stage 1 MCP and REST smoke paths inherit identity from remote auth.
        """

        if self._config.transport != "direct":
            return "remote-smoke"
        return question_scope_agent_id(self._config.run_id, self._config.question_id)

    async def initialize(self) -> None:
        """Initialize the configured transport stack for this adapter."""

        if self._config.transport == "direct":
            await self._initialize_direct()
            return

        if self._mcp_client is None:
            self._mcp_client = _build_mcp_client(
                base_url=self._config.mcp_base_url,
                headers=_auth_headers(self._config.auth_token),
            )
            await self._mcp_client.__aenter__()

        if self._config.transport == "rest" and self._http_client is None:
            self._http_client = httpx.AsyncClient(
                base_url=self._config.rest_base_url.rstrip("/"),
                headers=_auth_headers(self._config.auth_token),
                timeout=self._config.request_timeout_seconds,
            )

    async def close(self) -> None:
        """Release any owned transport resources."""

        if self._http_client is not None:
            await self._http_client.aclose()
            self._http_client = None

        if self._mcp_client is not None:
            await self._mcp_client.__aexit__(None, None, None)
            self._mcp_client = None

        if self._service_context is not None and self._owns_service_context:
            await shutdown_services(self._service_context)
            self._service_context = None

    async def __aenter__(self) -> NeoCortexAdapter:
        await self.initialize()
        return self

    async def __aexit__(self, *_exc_info: object) -> None:
        await self.close()

    async def ingest_sessions(self, sessions: list[Session]) -> IngestResult:
        """Store sessions via the configured transport."""

        if self._config.transport == "direct":
            return await self._ingest_direct(sessions)
        if self._config.transport == "mcp":
            return await self._ingest_mcp(sessions)
        return await self._ingest_rest(sessions)

    async def _ingest_direct(self, sessions: list[Session]) -> IngestResult:
        service_context = self._require_context()
        repo = self._repo
        embeddings = self._embeddings

        episode_ids: list[int] = []
        errors: list[str] = []

        for session in sessions:
            try:
                episode_id = await repo.store_episode(
                    agent_id=self.agent_id,
                    content=_serialize_session_content(session),
                    context=_serialize_session_context(
                        session,
                        run_id=self._config.run_id,
                        question_id=self._config.question_id,
                    ),
                    source_type="benchmark",
                )
                episode_ids.append(episode_id)

                if embeddings is not None:
                    vector = await embeddings.embed(_embedding_input_for_session(session))
                    if vector:
                        await repo.update_episode_embedding(episode_id, vector, self.agent_id)
            except Exception as exc:
                errors.append(f"Session {session.session_id}: {exc}")

        del service_context
        return IngestResult(
            episode_ids=episode_ids,
            sessions_ingested=len(episode_ids),
            errors=errors,
        )

    async def _ingest_mcp(self, sessions: list[Session]) -> IngestResult:
        mcp_client = self._require_mcp_client()
        episode_ids: list[int] = []
        errors: list[str] = []

        for session in sessions:
            try:
                result = await mcp_client.call_tool(
                    "remember",
                    {
                        "text": _serialize_session_content(session),
                        "context": _serialize_session_context(
                            session,
                            run_id=self._config.run_id,
                            question_id=self._config.question_id,
                        ),
                    },
                )
                parsed = RememberResult.model_validate(_mcp_payload(result))
                episode_ids.append(parsed.episode_id)
            except Exception as exc:
                errors.append(f"Session {session.session_id}: {exc}")

        return IngestResult(
            episode_ids=episode_ids,
            sessions_ingested=len(episode_ids),
            errors=errors,
        )

    async def _ingest_rest(self, sessions: list[Session]) -> IngestResult:
        http_client = self._require_http_client()
        errors: list[str] = []
        sessions_ingested = 0

        for session in sessions:
            try:
                response = await http_client.post(
                    "/ingest/text",
                    json={
                        "text": _serialize_session_content(session),
                        "metadata": _session_context_payload(
                            session,
                            run_id=self._config.run_id,
                            question_id=self._config.question_id,
                        ),
                    },
                )
                response.raise_for_status()
                parsed = RestIngestionResult.model_validate(response.json())
                if parsed.episodes_created < 1 or parsed.status == "failed":
                    raise RuntimeError(
                        "Ingestion API did not report a stored episode "
                        f"(status={parsed.status!r}, episodes_created={parsed.episodes_created})."
                    )
                sessions_ingested += 1
            except Exception as exc:
                errors.append(f"Session {session.session_id}: {exc}")

        return IngestResult(
            episode_ids=[],
            sessions_ingested=sessions_ingested,
            errors=errors,
        )

    async def await_indexing(self, result: IngestResult) -> None:
        """Yield control; direct writes are synchronous today."""

        del result
        await asyncio.sleep(0)

    async def search(self, query: str, limit: int = 10) -> list[SearchResult]:
        """Recall benchmark results via the configured transport."""

        if self._config.transport == "mcp":
            return await self._search_mcp(query, limit)
        if self._config.transport == "rest":
            return await self._search_mcp(query, limit)

        return await self._search_direct(query, limit)

    async def _search_direct(self, query: str, limit: int = 10) -> list[SearchResult]:
        self._require_context()
        repo = self._repo
        embeddings = self._embeddings

        query_embedding = None
        if embeddings is not None:
            query_embedding = await embeddings.embed(query)

        items = await repo.recall(
            query=query,
            agent_id=self.agent_id,
            limit=limit,
            query_embedding=query_embedding,
        )
        return [
            SearchResult(
                content=item.content,
                score=item.score,
                source=item.source or "",
                metadata={
                    "item_id": item.item_id,
                    "item_type": item.item_type,
                    "name": item.name,
                    "source_kind": item.source_kind,
                    "graph_name": item.graph_name,
                },
            )
            for item in items
        ]

    async def _search_mcp(self, query: str, limit: int = 10) -> list[SearchResult]:
        mcp_client = self._require_mcp_client()
        result = await mcp_client.call_tool("recall", {"query": query, "limit": limit})
        parsed = RecallResult.model_validate(_mcp_payload(result))
        return [
            SearchResult(
                content=item.content,
                score=item.score,
                source=item.source or "",
                metadata={
                    "item_id": item.item_id,
                    "item_type": item.item_type,
                    "name": item.name,
                    "source_kind": item.source_kind,
                    "graph_name": item.graph_name,
                },
            )
            for item in parsed.results
        ]

    async def clear(self) -> None:
        """Delete only this adapter's benchmark scope when the transport supports it."""

        if self._config.transport != "direct":
            # Stage 1 remote smoke transports do not expose delete primitives.
            # Run them against a fresh server/DB or a disposable token scope.
            await asyncio.sleep(0)
            return

        service_context = self._require_context()
        repo = service_context["repo"]

        if isinstance(repo, InMemoryRepository):
            repo._episodes = [episode for episode in repo._episodes if episode["agent_id"] != self.agent_id]
            return

        schema_mgr = service_context.get("schema_mgr")
        if schema_mgr is None:
            return

        for graph in await schema_mgr.list_graphs(agent_id=self.agent_id):
            await schema_mgr.drop_graph(graph.schema_name)

    def _require_context(self) -> ServiceContext:
        if self._service_context is None:
            raise RuntimeError("NeoCortexAdapter.initialize() must be called before use.")
        return self._service_context

    async def _initialize_direct(self) -> None:
        if self._service_context is not None:
            return

        settings = MCPSettings(auth_mode="none", mock_db=self._config.mock_db)
        self._service_context = await create_services(settings)
        self._owns_service_context = True

    @property
    def _repo(self) -> MemoryRepository:
        return self._require_context()["repo"]

    @property
    def _embeddings(self) -> EmbeddingService | None:
        return self._require_context().get("embeddings")

    def _require_mcp_client(self) -> Client:
        if self._mcp_client is None:
            raise RuntimeError("NeoCortexAdapter.initialize() must be called before MCP operations.")
        return self._mcp_client

    def _require_http_client(self) -> httpx.AsyncClient:
        if self._http_client is None:
            raise RuntimeError("NeoCortexAdapter.initialize() must be called before REST operations.")
        return self._http_client


def _serialize_session_content(session: Session) -> str:
    """Render one benchmark session into the stored episode body."""

    lines: list[str] = [f"session_id: {session.session_id}"]
    if session.timestamp is not None:
        lines.append(f"session_timestamp: {session.timestamp.isoformat(timespec='seconds')}")
    for message in session.messages:
        role = message.role.value
        if message.has_answer:
            role = f"{role} [has_answer]"
        lines.append(f"{role}: {message.content}")
    return "\n".join(lines)


def _session_context_payload(session: Session, *, run_id: str, question_id: str) -> dict[str, Any]:
    return {
        "benchmark": "longmemeval",
        "run_id": run_id,
        "question_id": question_id,
        "session_id": session.session_id,
        "session_timestamp": (
            session.timestamp.isoformat(timespec="seconds") if session.timestamp is not None else None
        ),
        "metadata": session.metadata,
    }


def _serialize_session_context(session: Session, *, run_id: str, question_id: str) -> str:
    """Preserve normalized benchmark metadata in the stored context payload."""

    payload = _session_context_payload(session, run_id=run_id, question_id=question_id)
    return json.dumps(payload, sort_keys=True, ensure_ascii=True)


def _embedding_input_for_session(session: Session) -> str:
    """Match remember semantics by embedding the episode text content."""

    return _serialize_session_content(session)


def _auth_headers(token: str | None) -> dict[str, str]:
    if not token:
        return {}
    return {"Authorization": f"Bearer {token}"}


def _build_mcp_client(*, base_url: str, headers: dict[str, str]) -> Client:
    transport = StreamableHttpTransport(url=f"{base_url.rstrip('/')}/mcp", headers=headers)
    return Client(transport=transport)


def _mcp_payload(result: Any) -> dict[str, Any]:
    if getattr(result, "is_error", False):
        raise RuntimeError(f"MCP tool call failed: {result}")

    structured = _coerce_mapping(getattr(result, "structured_content", None))
    if structured is not None:
        return structured

    parsed = _coerce_mapping(_parse_mcp_result(result))
    if parsed is not None:
        return parsed

    raise RuntimeError("MCP tool returned an unexpected payload shape.")


def _coerce_mapping(value: Any) -> dict[str, Any] | None:
    if isinstance(value, BaseModel):
        return value.model_dump()
    if isinstance(value, dict):
        return value
    if isinstance(value, list) and value:
        first = value[0]
        if isinstance(first, BaseModel):
            return first.model_dump()
        if isinstance(first, dict):
            return first
    return None


def _parse_mcp_result(result: Any) -> dict[str, Any]:
    if isinstance(result, dict):
        return result
    if isinstance(result, list) and result:
        first = result[0]
        if hasattr(first, "text"):
            try:
                return json.loads(first.text)
            except (json.JSONDecodeError, TypeError):
                return {"raw": first.text}
        if isinstance(first, dict):
            return first
    try:
        return json.loads(str(result))
    except (json.JSONDecodeError, TypeError):
        return {"raw": str(result)}


async def smoke_check_direct() -> None:
    """Minimal direct-path smoke check used by the Ralph verification step."""

    shared_context = await create_services(MCPSettings(auth_mode="none", mock_db=True))
    first = NeoCortexAdapter(
        NeoCortexConfig(run_id="smoke", question_id="question-a", mock_db=True),
        service_context=shared_context,
    )
    second = NeoCortexAdapter(
        NeoCortexConfig(run_id="smoke", question_id="question-b", mock_db=True),
        service_context=shared_context,
    )

    await first.initialize()
    await second.initialize()

    try:
        first_session = Session.model_validate(
            {
                "session_id": "smoke-a-1",
                "messages": [
                    {"role": "user", "content": "Alice likes oolong tea"},
                    {"role": "assistant", "content": "Stored for question A"},
                ],
            }
        )
        second_session = Session.model_validate(
            {
                "session_id": "smoke-b-1",
                "messages": [
                    {"role": "user", "content": "Bob prefers espresso"},
                    {"role": "assistant", "content": "Stored for question B"},
                ],
            }
        )

        await first.ingest_sessions([first_session])
        await second.ingest_sessions([second_session])

        first_results = await first.search("oolong", limit=5)
        second_results = await second.search("espresso", limit=5)
        leaked_results = await first.search("espresso", limit=5)

        if len(first_results) != 1 or "oolong" not in first_results[0].content.lower():
            raise RuntimeError("Direct smoke check failed for question A.")
        if len(second_results) != 1 or "espresso" not in second_results[0].content.lower():
            raise RuntimeError("Direct smoke check failed for question B.")
        if leaked_results:
            raise RuntimeError("Direct smoke check detected cross-question leakage.")
    finally:
        await shutdown_services(shared_context)
