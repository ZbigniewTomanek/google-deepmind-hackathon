"""Tests for Procrastinate job integration (Stage 2, Plan 07).

Uses InMemoryConnector — no Docker or PostgreSQL needed.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

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
    set_services(sentinel)  # type: ignore[arg-type]  # ty: ignore[invalid-argument-type]
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
    assert task.retry_strategy.max_attempts == 3  # ty: ignore[unresolved-attribute]


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
    import sys
    import types

    import neocortex.jobs.context as ctx_mod

    mock_repo = AsyncMock()
    mock_embeddings = AsyncMock()
    mock_settings = AsyncMock()
    mock_settings.ontology_model = "test-model"
    mock_settings.ontology_thinking_effort = "low"
    mock_settings.extractor_model = "test-model"
    mock_settings.extractor_thinking_effort = "low"
    mock_settings.librarian_model = "test-model"
    mock_settings.librarian_thinking_effort = "low"
    mock_settings.librarian_use_tools = True

    fake_ctx = {
        "repo": mock_repo,
        "embeddings": mock_embeddings,
        "settings": mock_settings,
    }
    ctx_mod._services = fake_ctx  # ty: ignore[invalid-assignment]

    # Create temporary mock modules so the lazy imports in the task succeed.
    mock_run = AsyncMock()
    fake_pipeline = types.ModuleType("neocortex.extraction.pipeline")
    fake_pipeline.run_extraction = mock_run  # type: ignore[attr-defined]  # ty: ignore[unresolved-attribute]

    fake_extraction = types.ModuleType("neocortex.extraction")

    # AgentInferenceConfig must be importable from the agents module
    from neocortex.extraction.agents import AgentInferenceConfig

    fake_agents = types.ModuleType("neocortex.extraction.agents")
    fake_agents.AgentInferenceConfig = (  # type: ignore[attr-defined]  # ty: ignore[unresolved-attribute]
        AgentInferenceConfig
    )

    sys.modules["neocortex.extraction"] = fake_extraction
    sys.modules["neocortex.extraction.pipeline"] = fake_pipeline
    sys.modules["neocortex.extraction.agents"] = fake_agents  # type: ignore[assignment]

    try:
        from neocortex.jobs.tasks import extract_episode

        # Call the task function directly (bypassing Procrastinate machinery)
        await extract_episode(agent_id="test-agent", episode_ids=[10, 20])

        mock_run.assert_called_once_with(
            repo=mock_repo,
            embeddings=mock_embeddings,
            agent_id="test-agent",
            episode_ids=[10, 20],
            target_schema=None,
            ontology_config=AgentInferenceConfig(
                model_name="test-model",
                thinking_effort="low",
            ),
            extractor_config=AgentInferenceConfig(
                model_name="test-model",
                thinking_effort="low",
            ),
            librarian_config=AgentInferenceConfig(
                model_name="test-model",
                thinking_effort="low",
            ),
            librarian_use_tools=True,
            domain_hint=None,
        )
    finally:
        ctx_mod._services = None
        sys.modules.pop("neocortex.extraction.pipeline", None)
        sys.modules.pop("neocortex.extraction.agents", None)
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
        worker_task = asyncio.create_task(app.run_worker_async(queues=["extraction"], install_signal_handlers=False))

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
    """MCPSettings has per-agent extraction settings with correct defaults."""
    from neocortex.mcp_settings import MCPSettings

    s = MCPSettings()
    assert s.extraction_enabled is True
    for prefix in ("ontology", "extractor", "librarian"):
        assert getattr(s, f"{prefix}_model") == "google-gla:gemini-3-flash-preview"
        assert getattr(s, f"{prefix}_thinking_effort") == "low"


# ── ServiceContext includes job_app ──


def test_service_context_type_has_job_app():
    """ServiceContext TypedDict includes job_app field."""
    from neocortex.services import ServiceContext

    # TypedDict annotations should include job_app
    annotations = ServiceContext.__annotations__
    assert "job_app" in annotations
