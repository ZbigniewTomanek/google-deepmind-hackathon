from contextlib import asynccontextmanager

from fastmcp import FastMCP
from starlette.responses import JSONResponse

from neocortex.auth import create_auth
from neocortex.config import PostgresConfig
from neocortex.db.adapter import GraphServiceAdapter
from neocortex.db.mock import InMemoryRepository
from neocortex.graph_service import GraphService
from neocortex.mcp_settings import MCPSettings
from neocortex.postgres_service import PostgresService


def create_server(settings: MCPSettings | None = None) -> FastMCP:
    settings = settings or MCPSettings()
    auth = create_auth(settings)

    @asynccontextmanager
    async def app_lifespan(server):
        del server
        if settings.mock_db:
            repo = InMemoryRepository()
            yield {"repo": repo, "settings": settings}
            return

        pg = PostgresService(PostgresConfig())
        await pg.connect()
        try:
            graph = GraphService(pg)
            repo = GraphServiceAdapter(graph, pool=pg.pool, pg=pg)
            yield {"repo": repo, "pg": pg, "graph": graph, "settings": settings}
        finally:
            await pg.disconnect()

    mcp = FastMCP(
        name=settings.server_name,
        auth=auth,
        instructions=(
            "NeoCortex is an agent memory system. Use 'remember' to store knowledge, "
            "'recall' to retrieve it, and 'discover' to explore what types of knowledge exist."
        ),
        lifespan=app_lifespan,
    )

    # Register tools
    from neocortex.tools import register_tools

    register_tools(mcp)

    # Health check
    @mcp.custom_route("/health", methods=["GET"])
    async def health_check(request):
        return JSONResponse({"status": "ok", "version": "0.1.0"})

    return mcp
