from __future__ import annotations

from typing import TypedDict

from neocortex.config import PostgresConfig
from neocortex.db.adapter import GraphServiceAdapter
from neocortex.db.mock import InMemoryRepository
from neocortex.embedding_service import EmbeddingService
from neocortex.graph_router import GraphRouter
from neocortex.graph_service import GraphService
from neocortex.mcp_settings import MCPSettings
from neocortex.postgres_service import PostgresService
from neocortex.schema_manager import SchemaManager


class ServiceContext(TypedDict):
    repo: GraphServiceAdapter | InMemoryRepository
    pg: PostgresService | None
    graph: GraphService | None
    schema_mgr: SchemaManager | None
    router: GraphRouter | None
    settings: MCPSettings
    embeddings: EmbeddingService | None


async def create_services(settings: MCPSettings) -> ServiceContext:
    """Initialize the full NeoCortex service stack.

    When ``settings.mock_db`` is True, returns an in-memory repository
    with ``None`` for all PostgreSQL-backed services.
    """
    if settings.mock_db:
        return ServiceContext(
            repo=InMemoryRepository(),
            pg=None,
            graph=None,
            schema_mgr=None,
            router=None,
            settings=settings,
            embeddings=None,
        )

    pg = PostgresService(PostgresConfig())
    await pg.connect()

    graph = GraphService(pg)
    schema_mgr = SchemaManager(pg)
    await schema_mgr.create_graph("shared", "knowledge", is_shared=True)
    router = GraphRouter(schema_mgr, pg.pool)
    repo = GraphServiceAdapter(graph, router=router, pool=pg.pool, pg=pg, settings=settings)
    embeddings = EmbeddingService(model=settings.embedding_model)

    return ServiceContext(
        repo=repo,
        pg=pg,
        graph=graph,
        schema_mgr=schema_mgr,
        router=router,
        settings=settings,
        embeddings=embeddings,
    )


async def shutdown_services(ctx: ServiceContext) -> None:
    """Shut down services, closing the PostgreSQL connection pool if open."""
    pg = ctx.get("pg")
    if pg is not None:
        await pg.disconnect()
