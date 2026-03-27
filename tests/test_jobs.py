"""Tests for Procrastinate job integration (Stage 2, Plan 07).

Uses InMemoryConnector — no Docker or PostgreSQL needed.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import procrastinate
import pytest
from procrastinate.testing import InMemoryConnector

from neocortex.jobs import create_job_app
from neocortex.jobs.context import get_services, set_services


# ── Job app factory ──


def test_create_job_app_returns_app():
    """create_job_app returns a properly configured Procrastinate App."""
    app = create_job_app("postgresql://user:pass@localhost:5432/testdb")
    assert isinstance(app, procrastinate.App)


# ── Context holder ──


def test_get_services_raises_before_set():
    """get_services raises RuntimeError if set_services was never called."""
    # Reset module state
    import neocortex.jobs.context as ctx_mod

    ctx_mod._services = None
    with pytest.raises(RuntimeError, match="not initialized"):
        get_services()


def test_set_and_get_services():
    """set_services / get_services round-trip works."""
    import neocortex.jobs.context as ctx_mod

    ctx_mod._services = None

    sentinel = {"repo": "fake", "settings": "fake"}
    set_services(sentinel)  # type: ignore[arg-type]
    assert get_services() is sentinel

    # Cleanup
    ctx_mod._services = None


# ── Task registration & deferral ──


@pytest.mark.asyncio
async def test_extract_episode_task_registered():
    """The extract_episode task is registered on the placeholder app."""
    from neocortex.jobs.tasks import app as placeholder_app

    task_names = [t.name for t in placeholder_app.tasks.values()]
    assert "extract_episode" in task_names


@pytest.mark.asyncio
async def test_extract_episode_task_has_retry():
    """extract_episode task has retry strategy with max_attempts=3."""
    from neocortex.jobs.tasks import app as placeholder_app

    task = placeholder_app.tasks["extract_episode"]
    assert task.retry_strategy is not None
    assert task.retry_strategy.max_attempts == 3


@pytest.mark.asyncio
async def test_extract_episode_task_queue():
    """extract_episode task is assigned to the 'extraction' queue."""
    from neocortex.jobs.tasks import app as placeholder_app

    task = placeholder_app.tasks["extract_episode"]
    assert task.queue == "extraction"


@pytest.mark.asyncio
async def test_defer_extract_episode():
    """Deferring extract_episode returns a valid job ID."""
    connector = InMemoryConnector()
    app = procrastinate.App(
        connector=connector,
        import_paths=["neocortex.jobs.tasks"],
    )

    await app.open_async()
    try:
        from neocortex.jobs.tasks import extract_episode

        job_id = await extract_episode.configure(app=app).defer_async(
            agent_id="test-agent",
            episode_ids=[1, 2, 3],
        )
        assert job_id is not None
        assert isinstance(job_id, int)
        assert job_id > 0

        # Deferring a second job yields a different ID
        job_id_2 = await extract_episode.configure(app=app).defer_async(
            agent_id="test-agent",
            episode_ids=[4, 5],
        )
        assert job_id_2 > job_id
    finally:
        await app.close_async()


@pytest.mark.asyncio
async def test_extract_episode_calls_run_extraction():
    """When the task executes, it calls run_extraction with correct args."""
    import types
    import sys

    import neocortex.jobs.context as ctx_mod

    mock_repo = AsyncMock()
    mock_embeddings = AsyncMock()
    mock_settings = AsyncMock()
    mock_settings.extraction_model = "test-model"

    fake_ctx = {
        "repo": mock_repo,
        "embeddings": mock_embeddings,
        "settings": mock_settings,
    }
    ctx_mod._services = fake_ctx

    # The extraction.pipeline module doesn't exist yet (Stage 4).
    # Create a temporary mock module so the lazy import in the task succeeds.
    mock_run = AsyncMock()
    fake_pipeline = types.ModuleType("neocortex.extraction.pipeline")
    fake_pipeline.run_extraction = mock_run  # type: ignore[attr-defined]

    # Also need the parent package
    fake_extraction = types.ModuleType("neocortex.extraction")

    sys.modules["neocortex.extraction"] = fake_extraction
    sys.modules["neocortex.extraction.pipeline"] = fake_pipeline

    try:
        from neocortex.jobs.tasks import extract_episode

        # Call the task function directly (bypassing Procrastinate machinery)
        await extract_episode(agent_id="test-agent", episode_ids=[10, 20])

        mock_run.assert_called_once_with(
            repo=mock_repo,
            embeddings=mock_embeddings,
            agent_id="test-agent",
            episode_ids=[10, 20],
            model_name="test-model",
        )
    finally:
        ctx_mod._services = None
        sys.modules.pop("neocortex.extraction.pipeline", None)
        sys.modules.pop("neocortex.extraction", None)


# ── Worker lifecycle ──


@pytest.mark.asyncio
async def test_worker_starts_and_stops():
    """Worker can be started as an asyncio task and cancelled cleanly."""
    connector = InMemoryConnector()
    app = procrastinate.App(
        connector=connector,
        import_paths=["neocortex.jobs.tasks"],
    )

    await app.open_async()
    try:
        worker_task = asyncio.create_task(
            app.run_worker_async(
                queues=["extraction"], install_signal_handlers=False
            )
        )

        # Give the worker a moment to start
        await asyncio.sleep(0.05)
        assert not worker_task.done()

        # Cancel and verify clean shutdown
        worker_task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await worker_task
    finally:
        await app.close_async()


# ── Settings ──


def test_extraction_settings_defaults():
    """MCPSettings has extraction_enabled and extraction_model with correct defaults."""
    from neocortex.mcp_settings import MCPSettings

    s = MCPSettings()
    assert s.extraction_enabled is True
    assert s.extraction_model == "gemini-2.5-flash"


# ── ServiceContext includes job_app ──


def test_service_context_type_has_job_app():
    """ServiceContext TypedDict includes job_app field."""
    from neocortex.services import ServiceContext

    # TypedDict annotations should include job_app
    annotations = ServiceContext.__annotations__
    assert "job_app" in annotations
