import asyncio
from contextlib import asynccontextmanager, suppress

from fastmcp import FastMCP
from starlette.responses import JSONResponse

from neocortex.auth import create_auth
from neocortex.mcp_settings import MCPSettings
from neocortex.services import create_services, shutdown_services


def create_server(settings: MCPSettings | None = None) -> FastMCP:
    settings = settings or MCPSettings()
    auth = create_auth(settings)

    @asynccontextmanager
    async def app_lifespan(server):
        del server
        ctx = await create_services(settings)
        job_app = ctx.get("job_app")

        # Start Procrastinate worker in MCP server only (ingestion API just enqueues)
        worker_task = None
        if job_app is not None:
            worker_task = asyncio.create_task(
                job_app.run_worker_async(
                    queues=["extraction"],
                    concurrency=settings.worker_concurrency,
                    fetch_job_polling_interval=settings.worker_polling_interval,
                    install_signal_handlers=False,
                )
            )

        try:
            yield ctx
        finally:
            if worker_task is not None:
                worker_task.cancel()
                with suppress(asyncio.CancelledError):
                    await worker_task
            await shutdown_services(ctx)

    mcp = FastMCP(
        name=settings.server_name,
        auth=auth,
        instructions=(
            "NeoCortex is an agent memory system. Use 'remember' to store knowledge, "
            "'recall' to retrieve it, and the discover_* tools to explore what knowledge exists: "
            "discover_domains → discover_graphs → discover_ontology → discover_details."
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
