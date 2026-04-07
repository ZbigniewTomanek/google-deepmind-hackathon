"""Tests for the DomainRouter — classification, permissions, provisioning."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from neocortex.domains import InMemoryDomainService
from neocortex.domains.classifier import MockDomainClassifier
from neocortex.domains.models import (
    ClassificationResult,
    DomainClassification,
    ProposedDomain,
)
from neocortex.domains.router import DomainRouter
from neocortex.permissions.memory_service import InMemoryPermissionService


@pytest.fixture
async def domain_service() -> InMemoryDomainService:
    svc = InMemoryDomainService()
    await svc.seed_defaults()
    return svc


@pytest.fixture
def permissions() -> InMemoryPermissionService:
    return InMemoryPermissionService(bootstrap_admin_id="admin_agent")


@pytest.fixture
def classifier() -> MockDomainClassifier:
    return MockDomainClassifier()


@pytest.fixture
def mock_schema_mgr() -> AsyncMock:
    """Mock SchemaManager that returns predictable schema names."""
    mgr = AsyncMock()
    mgr.create_graph = AsyncMock(side_effect=lambda agent_id, purpose, is_shared=False: f"ncx_{agent_id}__{purpose}")
    return mgr


class TestRouteAndExtract:
    @pytest.mark.asyncio
    async def test_routes_to_matched_domains(
        self,
        domain_service: InMemoryDomainService,
        classifier: MockDomainClassifier,
        permissions: InMemoryPermissionService,
    ) -> None:
        """'I prefer Python' matches user_profile + technical_knowledge."""
        # Grant write to both schemas
        await permissions.grant("agent1", "ncx_shared__user_profile", True, True, "test")
        await permissions.grant("agent1", "ncx_shared__technical_knowledge", True, True, "test")

        router = DomainRouter(
            domain_service=domain_service,
            classifier=classifier,
            schema_mgr=None,
            permissions=permissions,
        )
        results = await router.route_and_extract("agent1", 1, "I prefer Python for backend work")
        slugs = {r.domain_slug for r in results}
        assert "user_profile" in slugs
        assert "technical_knowledge" in slugs
        for r in results:
            assert r.schema_name.startswith("ncx_shared__")

    @pytest.mark.asyncio
    async def test_agent_without_write_permission_skipped(
        self,
        domain_service: InMemoryDomainService,
        classifier: MockDomainClassifier,
        permissions: InMemoryPermissionService,
    ) -> None:
        """Agent without write permission to user_profile — that schema is skipped."""
        # Only grant technical_knowledge, not user_profile
        await permissions.grant("agent1", "ncx_shared__technical_knowledge", True, True, "test")

        router = DomainRouter(
            domain_service=domain_service,
            classifier=classifier,
            schema_mgr=None,
            permissions=permissions,
        )
        results = await router.route_and_extract("agent1", 1, "I prefer Python for backend work")
        slugs = {r.domain_slug for r in results}
        assert "user_profile" not in slugs
        assert "technical_knowledge" in slugs

    @pytest.mark.asyncio
    async def test_admin_routes_to_all_matched(
        self,
        domain_service: InMemoryDomainService,
        classifier: MockDomainClassifier,
        permissions: InMemoryPermissionService,
    ) -> None:
        """Admin agent bypasses permission checks, routes to all matched schemas."""
        await permissions.ensure_admin("admin_agent")

        router = DomainRouter(
            domain_service=domain_service,
            classifier=classifier,
            schema_mgr=None,
            permissions=permissions,
        )
        results = await router.route_and_extract("admin_agent", 1, "I prefer Python for backend work")
        slugs = {r.domain_slug for r in results}
        assert "user_profile" in slugs
        assert "technical_knowledge" in slugs

    @pytest.mark.asyncio
    async def test_classification_below_threshold_filtered(
        self,
        domain_service: InMemoryDomainService,
        permissions: InMemoryPermissionService,
    ) -> None:
        """Matches below classification threshold are filtered out."""
        # Create a classifier that returns low confidence
        low_conf_classifier = AsyncMock()
        low_conf_classifier.classify = AsyncMock(
            return_value=ClassificationResult(
                matched_domains=[
                    DomainClassification(domain_slug="user_profile", confidence=0.1, reasoning="weak"),
                    DomainClassification(domain_slug="technical_knowledge", confidence=0.5, reasoning="strong"),
                ]
            )
        )
        await permissions.grant("agent1", "ncx_shared__user_profile", True, True, "test")
        await permissions.grant("agent1", "ncx_shared__technical_knowledge", True, True, "test")

        router = DomainRouter(
            domain_service=domain_service,
            classifier=low_conf_classifier,
            schema_mgr=None,
            permissions=permissions,
            classification_threshold=0.3,
        )
        results = await router.route_and_extract("agent1", 1, "text")
        slugs = {r.domain_slug for r in results}
        assert "user_profile" not in slugs
        assert "technical_knowledge" in slugs

    @pytest.mark.asyncio
    async def test_classifier_exception_returns_empty(
        self,
        domain_service: InMemoryDomainService,
        permissions: InMemoryPermissionService,
    ) -> None:
        """Classifier raising exception → graceful degradation, returns []."""
        failing_classifier = AsyncMock()
        failing_classifier.classify = AsyncMock(side_effect=RuntimeError("model unavailable"))

        router = DomainRouter(
            domain_service=domain_service,
            classifier=failing_classifier,
            schema_mgr=None,
            permissions=permissions,
        )
        results = await router.route_and_extract("agent1", 1, "any text")
        assert results == []


class TestDomainProvisioning:
    @pytest.mark.asyncio
    async def test_proposed_domain_provisioned(
        self,
        domain_service: InMemoryDomainService,
        permissions: InMemoryPermissionService,
        mock_schema_mgr: AsyncMock,
    ) -> None:
        """Classifier proposes new domain → domain created, schema provisioned, agent gets permissions."""
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
            domain_service=domain_service,
            classifier=proposing_classifier,
            schema_mgr=mock_schema_mgr,
            permissions=permissions,
        )
        results = await router.route_and_extract("agent1", 1, "I run 5km every morning")

        assert len(results) == 1
        assert results[0].domain_slug == "health_wellness"
        assert results[0].schema_name == "ncx_shared__health_wellness"

        # Verify domain was created in service
        domain = await domain_service.get_domain("health_wellness")
        assert domain is not None
        assert domain.schema_name == "ncx_shared__health_wellness"

        # Verify agent got permissions
        can_write = await permissions.can_write_schema("agent1", "ncx_shared__health_wellness")
        assert can_write

    @pytest.mark.asyncio
    async def test_provisioning_skipped_without_schema_mgr(
        self,
        domain_service: InMemoryDomainService,
        permissions: InMemoryPermissionService,
    ) -> None:
        """When schema_mgr=None, proposed domain is ignored (no error)."""
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
            domain_service=domain_service,
            classifier=proposing_classifier,
            schema_mgr=None,
            permissions=permissions,
        )
        results = await router.route_and_extract("agent1", 1, "I run 5km every morning")
        assert results == []


class TestEmptyDomains:
    @pytest.mark.asyncio
    async def test_router_handles_empty_domains(
        self,
        permissions: InMemoryPermissionService,
    ) -> None:
        """Router should return empty list when domain service has no domains."""
        empty_domain_service = InMemoryDomainService()
        # Do NOT seed defaults — domains list will be empty

        router = DomainRouter(
            domain_service=empty_domain_service,
            classifier=MockDomainClassifier(),
            schema_mgr=None,
            permissions=permissions,
        )
        results = await router.route_and_extract("agent1", 1, "some text about Python")
        assert results == []


class TestDomainProvisioningWithParent:
    @pytest.mark.asyncio
    async def test_proposed_domain_with_valid_parent_slug(
        self,
        domain_service: InMemoryDomainService,
        permissions: InMemoryPermissionService,
        mock_schema_mgr: AsyncMock,
    ) -> None:
        """Proposed domain with parent_slug resolves parent_id and creates child domain."""
        proposing_classifier = AsyncMock()
        proposing_classifier.classify = AsyncMock(
            return_value=ClassificationResult(
                matched_domains=[],
                proposed_domain=ProposedDomain(
                    slug="python",
                    name="Python",
                    description="Python programming",
                    reasoning="Specific technical subdomain",
                    parent_slug="technical_knowledge",
                ),
            )
        )

        router = DomainRouter(
            domain_service=domain_service,
            classifier=proposing_classifier,
            schema_mgr=mock_schema_mgr,
            permissions=permissions,
        )
        results = await router.route_and_extract("agent1", 1, "Python asyncio patterns")

        assert len(results) == 1
        assert results[0].domain_slug == "python"

        # Verify hierarchy
        domain = await domain_service.get_domain("python")
        assert domain is not None
        parent = await domain_service.get_domain("technical_knowledge")
        assert parent is not None
        assert domain.parent_id == parent.id
        assert domain.depth == 1
        assert domain.path == "technical_knowledge.python"

    @pytest.mark.asyncio
    async def test_proposed_domain_with_invalid_parent_slug_creates_root(
        self,
        domain_service: InMemoryDomainService,
        permissions: InMemoryPermissionService,
        mock_schema_mgr: AsyncMock,
    ) -> None:
        """Proposed domain with nonexistent parent_slug creates a root domain (D3)."""
        proposing_classifier = AsyncMock()
        proposing_classifier.classify = AsyncMock(
            return_value=ClassificationResult(
                matched_domains=[],
                proposed_domain=ProposedDomain(
                    slug="cooking",
                    name="Cooking",
                    description="Cooking knowledge",
                    reasoning="Novel domain",
                    parent_slug="nonexistent_parent",
                ),
            )
        )

        router = DomainRouter(
            domain_service=domain_service,
            classifier=proposing_classifier,
            schema_mgr=mock_schema_mgr,
            permissions=permissions,
        )
        results = await router.route_and_extract("agent1", 1, "Making sourdough bread")

        assert len(results) == 1
        domain = await domain_service.get_domain("cooking")
        assert domain is not None
        assert domain.parent_id is None
        assert domain.depth == 0
        assert domain.path == "cooking"


class TestUnmatchedTextReturnsEmpty:
    @pytest.mark.asyncio
    async def test_unmatched_text_no_fallback(
        self,
        domain_service: InMemoryDomainService,
        classifier: MockDomainClassifier,
        permissions: InMemoryPermissionService,
    ) -> None:
        """Unmatched text returns empty results — no silent domain_knowledge fallback."""
        router = DomainRouter(
            domain_service=domain_service,
            classifier=classifier,
            schema_mgr=None,
            permissions=permissions,
        )
        results = await router.route_and_extract("agent1", 1, "The weather is beautiful today")
        assert results == []


class TestEnsureSchema:
    @pytest.mark.asyncio
    async def test_idempotent_for_seeded_domains(
        self,
        domain_service: InMemoryDomainService,
        classifier: MockDomainClassifier,
        permissions: InMemoryPermissionService,
    ) -> None:
        """Calling route twice for the same domain doesn't error."""
        await permissions.grant("agent1", "ncx_shared__work_context", True, True, "test")

        router = DomainRouter(
            domain_service=domain_service,
            classifier=classifier,
            schema_mgr=None,
            permissions=permissions,
        )
        text = "We have a team meeting about the project deadline"
        results1 = await router.route_and_extract("agent1", 1, text)
        results2 = await router.route_and_extract("agent1", 2, text)
        assert len(results1) > 0
        assert len(results2) > 0

    @pytest.mark.asyncio
    async def test_ensure_schema_returns_none_without_schema_mgr(
        self,
        domain_service: InMemoryDomainService,
        permissions: InMemoryPermissionService,
    ) -> None:
        """Domain without schema_name and no schema_mgr → schema is None, domain skipped."""
        # Create a domain without schema_name
        await domain_service.create_domain(slug="orphan", name="Orphan", description="No schema", created_by="test")

        classifier_with_orphan = AsyncMock()
        classifier_with_orphan.classify = AsyncMock(
            return_value=ClassificationResult(
                matched_domains=[
                    DomainClassification(domain_slug="orphan", confidence=0.9, reasoning="direct match"),
                ]
            )
        )

        router = DomainRouter(
            domain_service=domain_service,
            classifier=classifier_with_orphan,
            schema_mgr=None,
            permissions=permissions,
        )
        results = await router.route_and_extract("agent1", 1, "text")
        assert results == []
