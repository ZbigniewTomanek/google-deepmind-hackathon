"""Integration tests for domain routing pipeline — cross-cutting flows.

Covers end-to-end routing through all components, domain provisioning
lifecycle, and pipeline integration (remember tool + ingestion processor).
Avoids duplicating unit tests from test_domain_models, test_domain_classifier,
and test_domain_router.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from neocortex.db.mock import InMemoryRepository
from neocortex.domains import InMemoryDomainService
from neocortex.domains.classifier import MockDomainClassifier
from neocortex.domains.models import (
    ClassificationResult,
    ProposedDomain,
)
from neocortex.domains.router import DomainRouter
from neocortex.ingestion.episode_processor import EpisodeProcessor
from neocortex.mcp_settings import MCPSettings
from neocortex.permissions.memory_service import InMemoryPermissionService

# ── Helpers ──


def _make_mock_job_app(return_value: int = 42) -> MagicMock:
    """Create a mock job_app whose configure_task(...).defer_async(...) returns return_value."""
    mock_job_app = MagicMock()
    mock_deferrer = MagicMock()
    mock_deferrer.defer_async = AsyncMock(return_value=return_value)
    mock_job_app.configure_task.return_value = mock_deferrer
    return mock_job_app


async def _build_routing_stack(
    *,
    admin_id: str = "admin_agent",
    schema_mgr: AsyncMock | None = None,
    job_app: MagicMock | None = None,
    threshold: float = 0.3,
) -> tuple[DomainRouter, InMemoryDomainService, InMemoryPermissionService]:
    """Build a full routing stack with in-memory services."""
    domain_svc = InMemoryDomainService()
    await domain_svc.seed_defaults()
    permissions = InMemoryPermissionService(bootstrap_admin_id=admin_id)
    classifier = MockDomainClassifier()

    router = DomainRouter(
        domain_service=domain_svc,
        classifier=classifier,
        schema_mgr=schema_mgr,
        permissions=permissions,
        job_app=job_app,
        classification_threshold=threshold,
    )
    return router, domain_svc, permissions


# ── TestFullRoutingPipeline ──


class TestFullRoutingPipeline:
    """End-to-end flow through classification → permissions → routing results."""

    @pytest.mark.asyncio
    async def test_episode_classified_and_routed(self) -> None:
        """Text flows from classification through permission check to RoutingResult with correct schema names."""
        router, _, permissions = await _build_routing_stack()

        # Grant write to work_context schema
        await permissions.grant("agent1", "ncx_shared__work_context", True, True, "test")

        results = await router.route_and_extract("agent1", 1, "We have a team meeting about the sprint deadline")

        assert len(results) >= 1
        schema_names = {r.schema_name for r in results}
        assert "ncx_shared__work_context" in schema_names
        # All results should have valid schema names and confidence
        for r in results:
            assert r.schema_name.startswith("ncx_shared__")
            assert r.confidence >= 0.3

    @pytest.mark.asyncio
    async def test_multi_domain_episode(self) -> None:
        """'I prefer Python for my project deadline' routes to 2+ domain schemas."""
        router, _, permissions = await _build_routing_stack()

        # Grant write to all seed schemas
        for slug in ("user_profile", "technical_knowledge", "work_context", "domain_knowledge"):
            await permissions.grant("agent1", f"ncx_shared__{slug}", True, True, "test")

        results = await router.route_and_extract("agent1", 1, "I prefer Python for my project deadline")

        slugs = {r.domain_slug for r in results}
        # Should match at least user_profile ("prefer"), technical_knowledge ("python"),
        # and work_context ("project", "deadline")
        assert len(slugs) >= 2
        assert "user_profile" in slugs
        assert "technical_knowledge" in slugs
        assert "work_context" in slugs

    @pytest.mark.asyncio
    async def test_admin_routes_to_all_matched(self) -> None:
        """Admin agent bypasses permission checks, routes to all matched schemas."""
        router, _, permissions = await _build_routing_stack(admin_id="admin_agent")
        await permissions.ensure_admin("admin_agent")

        # No explicit grants — admin bypasses all permission checks
        results = await router.route_and_extract("admin_agent", 1, "I prefer Python for my project deadline")

        slugs = {r.domain_slug for r in results}
        assert len(slugs) >= 2
        # Admin gets all matched domains without explicit grants
        assert "user_profile" in slugs
        assert "technical_knowledge" in slugs


# ── TestDomainProvisioning ──


class TestDomainProvisioning:
    """New domain lifecycle: propose → create → provision → route."""

    @pytest.mark.asyncio
    async def test_new_domain_created_and_routed(self) -> None:
        """Proposed domain created in service, schema provisioned, agent gets permissions, routing result returned."""
        mock_schema_mgr = AsyncMock()
        mock_schema_mgr.create_graph = AsyncMock(
            side_effect=lambda agent_id, purpose, is_shared=False: f"ncx_{agent_id}__{purpose}"
        )

        domain_svc = InMemoryDomainService()
        await domain_svc.seed_defaults()
        permissions = InMemoryPermissionService(bootstrap_admin_id="admin")

        # Classifier that proposes a new domain
        proposing_classifier = AsyncMock()
        proposing_classifier.classify = AsyncMock(
            return_value=ClassificationResult(
                matched_domains=[],
                proposed_domain=ProposedDomain(
                    slug="health_wellness",
                    name="Health & Wellness",
                    description="Health-related knowledge",
                    reasoning="Does not fit existing domains",
                ),
            )
        )

        router = DomainRouter(
            domain_service=domain_svc,
            classifier=proposing_classifier,
            schema_mgr=mock_schema_mgr,
            permissions=permissions,
        )

        results = await router.route_and_extract("agent1", 1, "I run 5km every morning")

        # Domain was created and routed
        assert len(results) == 1
        assert results[0].domain_slug == "health_wellness"
        assert results[0].schema_name == "ncx_shared__health_wellness"

        # Domain persisted in service with schema_name
        domain = await domain_svc.get_domain("health_wellness")
        assert domain is not None
        assert domain.schema_name == "ncx_shared__health_wellness"

        # Agent got write permissions
        can_write = await permissions.can_write_schema("agent1", "ncx_shared__health_wellness")
        assert can_write

        # Schema manager was called
        mock_schema_mgr.create_graph.assert_called()

    @pytest.mark.asyncio
    async def test_provisioning_skipped_without_schema_mgr(self) -> None:
        """When schema_mgr=None (mock mode), proposed domain does not cause error."""
        domain_svc = InMemoryDomainService()
        await domain_svc.seed_defaults()
        permissions = InMemoryPermissionService(bootstrap_admin_id="admin")

        proposing_classifier = AsyncMock()
        proposing_classifier.classify = AsyncMock(
            return_value=ClassificationResult(
                matched_domains=[],
                proposed_domain=ProposedDomain(
                    slug="health_wellness",
                    name="Health & Wellness",
                    description="Health-related knowledge",
                    reasoning="Does not fit existing domains",
                ),
            )
        )

        router = DomainRouter(
            domain_service=domain_svc,
            classifier=proposing_classifier,
            schema_mgr=None,  # No schema manager
            permissions=permissions,
        )

        # Should not error, just return empty results
        results = await router.route_and_extract("agent1", 1, "I run 5km every morning")
        assert results == []

        # Domain was NOT created
        domain = await domain_svc.get_domain("health_wellness")
        assert domain is None


# ── TestPipelineIntegration ──


class TestPipelineIntegration:
    """Remember tool and ingestion processor wiring with domain routing."""

    @pytest.mark.asyncio
    async def test_remember_enqueues_routing(self) -> None:
        """Remember tool with no target_graph enqueues route_episode."""
        repo = InMemoryRepository()
        settings = MCPSettings(mock_db=True, extraction_enabled=True, domain_routing_enabled=True)
        mock_job_app = _make_mock_job_app(return_value=42)

        ctx = MagicMock()
        ctx.lifespan_context = {
            "repo": repo,
            "settings": settings,
            "embeddings": None,
            "job_app": mock_job_app,
        }

        with patch(
            "neocortex.tools.remember.get_agent_id_from_context",
            return_value="test-agent",
        ):
            from neocortex.tools.remember import remember

            result = await remember("I prefer Python for backend work", ctx=ctx)

        assert result.status == "stored"

        # Should have called configure_task for both extract_episode and route_episode
        task_names = [call.args[0] for call in mock_job_app.configure_task.call_args_list]
        assert "extract_episode" in task_names
        assert "route_episode" in task_names

    @pytest.mark.asyncio
    async def test_remember_explicit_target_skips_routing(self) -> None:
        """Remember tool with target_graph does NOT enqueue routing."""
        repo = InMemoryRepository()
        settings = MCPSettings(mock_db=True, extraction_enabled=True, domain_routing_enabled=True)
        mock_job_app = _make_mock_job_app(return_value=42)

        ctx = MagicMock()
        ctx.lifespan_context = {
            "repo": repo,
            "settings": settings,
            "embeddings": None,
            "job_app": mock_job_app,
            "router": MagicMock(route_store_to=AsyncMock()),
        }

        with patch(
            "neocortex.tools.remember.get_agent_id_from_context",
            return_value="test-agent",
        ):
            from neocortex.tools.remember import remember

            result = await remember(
                "I prefer Python",
                target_graph="ncx_shared__knowledge",
                ctx=ctx,
            )

        assert result.status == "stored"

        # Should have extract_episode but NOT route_episode
        task_names = [call.args[0] for call in mock_job_app.configure_task.call_args_list]
        assert "extract_episode" in task_names
        assert "route_episode" not in task_names

    @pytest.mark.asyncio
    async def test_ingestion_enqueues_routing(self) -> None:
        """EpisodeProcessor enqueues routing after extraction."""
        repo = InMemoryRepository()
        mock_job_app = _make_mock_job_app(return_value=99)

        processor = EpisodeProcessor(
            repo=repo,
            job_app=mock_job_app,
            extraction_enabled=True,
            domain_routing_enabled=True,
        )
        result = await processor.process_text("agent-a", "Python API design patterns", {})

        assert result.status == "stored"

        # Should have called configure_task for both extract_episode and route_episode
        task_names = [call.args[0] for call in mock_job_app.configure_task.call_args_list]
        assert "extract_episode" in task_names
        assert "route_episode" in task_names

    @pytest.mark.asyncio
    async def test_routing_disabled(self) -> None:
        """When domain_routing_enabled=False, no routing jobs enqueued."""
        repo = InMemoryRepository()
        mock_job_app = _make_mock_job_app(return_value=99)

        processor = EpisodeProcessor(
            repo=repo,
            job_app=mock_job_app,
            extraction_enabled=True,
            domain_routing_enabled=False,
        )
        result = await processor.process_text("agent-a", "Python API design patterns", {})

        assert result.status == "stored"

        # Only extract_episode, NOT route_episode
        task_names = [call.args[0] for call in mock_job_app.configure_task.call_args_list]
        assert "extract_episode" in task_names
        assert "route_episode" not in task_names

    @pytest.mark.asyncio
    async def test_backward_compat(self) -> None:
        """Existing personal graph extraction still happens alongside routing."""
        repo = InMemoryRepository()
        settings = MCPSettings(mock_db=True, extraction_enabled=True, domain_routing_enabled=True)
        mock_job_app = _make_mock_job_app(return_value=42)

        ctx = MagicMock()
        ctx.lifespan_context = {
            "repo": repo,
            "settings": settings,
            "embeddings": None,
            "job_app": mock_job_app,
        }

        with patch(
            "neocortex.tools.remember.get_agent_id_from_context",
            return_value="test-agent",
        ):
            from neocortex.tools.remember import remember

            result = await remember("Learn about Python frameworks", ctx=ctx)

        assert result.status == "stored"
        # extraction_job_id comes from the extract_episode call
        assert result.extraction_job_id == 42

        # Both extraction and routing were enqueued
        task_names = [call.args[0] for call in mock_job_app.configure_task.call_args_list]
        assert "extract_episode" in task_names
        assert "route_episode" in task_names

        # extract_episode was called with target_schema=None (personal graph)
        extract_calls = [
            call for call in mock_job_app.configure_task.call_args_list if call.args[0] == "extract_episode"
        ]
        assert len(extract_calls) == 1
        defer_call = mock_job_app.configure_task.return_value.defer_async
        # The first defer_async call is for extraction (personal graph)
        first_call_kwargs = defer_call.call_args_list[0][1]
        assert first_call_kwargs["target_schema"] is None
