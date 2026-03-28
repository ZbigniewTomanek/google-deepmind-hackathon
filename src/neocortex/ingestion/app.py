from __future__ import annotations

import os
import shutil
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from loguru import logger

from neocortex.admin.routes import router as admin_router
from neocortex.auth.tokens import load_token_map
from neocortex.ingestion.episode_processor import EpisodeProcessor
from neocortex.ingestion.media_store import MediaFileStore
from neocortex.ingestion.routes import router
from neocortex.mcp_settings import MCPSettings
from neocortex.services import create_services, shutdown_services


def create_app(settings: MCPSettings | None = None) -> FastAPI:
    settings = settings or MCPSettings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        ctx = await create_services(settings)

        # --- Media services ---
        media_store = MediaFileStore(settings.media_store_path)

        if settings.mock_db:
            from neocortex.ingestion.media_compressor_mock import MockMediaCompressor
            from neocortex.ingestion.media_description_mock import MockMediaDescriptionService

            media_compressor = MockMediaCompressor()
            media_describer = MockMediaDescriptionService()
        elif shutil.which("ffmpeg"):
            from neocortex.ingestion.media_compressor import MediaCompressor
            from neocortex.ingestion.media_description import MediaDescriptionService

            media_compressor = MediaCompressor()
            media_describer = MediaDescriptionService(
                api_key=os.environ.get("GOOGLE_API_KEY", ""),
                model=settings.media_description_model,
                max_output_tokens=settings.media_description_max_tokens,
            )
        else:
            logger.warning("ffmpeg not found on PATH — media ingestion disabled")
            media_compressor = None
            media_describer = None

        processor = EpisodeProcessor(
            repo=ctx["repo"],
            embeddings=ctx.get("embeddings"),
            job_app=ctx.get("job_app"),
            extraction_enabled=settings.extraction_enabled,
            media_store=media_store,
            media_compressor=media_compressor,
            media_describer=media_describer,
            domain_routing_enabled=settings.domain_routing_enabled,
        )

        app.state.services_ctx = ctx
        app.state.processor = processor
        app.state.settings = settings
        app.state.permissions = ctx["permissions"]
        app.state.schema_mgr = ctx.get("schema_mgr")

        token_map = load_token_map(settings)
        # Ensure bootstrap admin token maps to the bootstrap admin agent_id
        if settings.admin_token and settings.admin_token not in token_map:
            token_map[settings.admin_token] = settings.bootstrap_admin_id
        app.state.token_map = token_map

        if settings.auth_mode == "auth0":
            from neocortex.ingestion.auth0_jwt import Auth0JWTVerifier

            app.state.auth0_verifier = Auth0JWTVerifier(
                domain=settings.auth0_domain,
                audience=settings.auth0_audience,
            )

        try:
            yield
        finally:
            await shutdown_services(ctx)

    app = FastAPI(title="NeoCortex Ingestion API", version="0.1.0", lifespan=lifespan)

    @app.get("/health")
    async def health():
        return JSONResponse({"status": "ok", "version": "0.1.0"})

    app.include_router(router)
    app.include_router(admin_router)

    return app
