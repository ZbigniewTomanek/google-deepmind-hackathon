from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from neocortex.auth.tokens import load_token_map
from neocortex.ingestion.episode_processor import EpisodeProcessor
from neocortex.ingestion.routes import router
from neocortex.mcp_settings import MCPSettings
from neocortex.services import create_services, shutdown_services


def create_app(settings: MCPSettings | None = None) -> FastAPI:
    settings = settings or MCPSettings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        ctx = await create_services(settings)
        processor = EpisodeProcessor(
            repo=ctx["repo"],
            embeddings=ctx.get("embeddings"),
            job_app=ctx.get("job_app"),
            extraction_enabled=settings.extraction_enabled,
        )

        app.state.services_ctx = ctx
        app.state.processor = processor
        app.state.settings = settings
        app.state.permissions = ctx["permissions"]
        app.state.token_map = load_token_map(settings)

        try:
            yield
        finally:
            await shutdown_services(ctx)

    app = FastAPI(title="NeoCortex Ingestion API", version="0.1.0", lifespan=lifespan)

    @app.get("/health")
    async def health():
        return JSONResponse({"status": "ok", "version": "0.1.0"})

    app.include_router(router)

    return app
