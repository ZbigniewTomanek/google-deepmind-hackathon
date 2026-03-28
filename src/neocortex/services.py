from __future__ import annotations

import contextlib
from typing import TypedDict

import procrastinate
import procrastinate.exceptions

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
    job_app: procrastinate.App | None


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
            job_app=None,
        )

    pg_config = PostgresConfig()
    pg = PostgresService(pg_config)
    await pg.connect()

    graph = GraphService(pg)
    schema_mgr = SchemaManager(pg)
    await schema_mgr.create_graph("shared", "knowledge", is_shared=True)
    router = GraphRouter(schema_mgr, pg.pool)
    repo = GraphServiceAdapter(graph, router=router, pool=pg.pool, pg=pg, settings=settings)
    embeddings = EmbeddingService(model=settings.embedding_model)

    # Procrastinate job queue (only when extraction is enabled with real DB)
    job_app: procrastinate.App | None = None
    if settings.extraction_enabled:
        from neocortex.jobs import create_job_app

        job_app = create_job_app(pg_config.dsn)
        await job_app.open_async()
        with contextlib.suppress(procrastinate.exceptions.ConnectorException):
            await job_app.schema_manager.apply_schema_async()

    ctx = ServiceContext(
        repo=repo,
        pg=pg,
        graph=graph,
        schema_mgr=schema_mgr,
        router=router,
        settings=settings,
        embeddings=embeddings,
        job_app=job_app,
    )

    # Make services available to Procrastinate task handlers
    if job_app is not None:
        from neocortex.jobs.context import set_services

        set_services(ctx)

    return ctx


async def shutdown_services(ctx: ServiceContext) -> None:
    """Shut down services, closing the PostgreSQL connection pool if open."""
    job_app = ctx.get("job_app")
    if job_app is not None:
        await job_app.close_async()

    pg = ctx.get("pg")
    if pg is not None:
        await pg.disconnect()
