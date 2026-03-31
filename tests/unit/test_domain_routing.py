"""Unit tests for DomainRouter permission grants (Plan 19, M5)."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
import pytest_asyncio

from neocortex.domains.classifier import DomainClassifier
from neocortex.domains.memory_service import InMemoryDomainService
from neocortex.domains.models import ClassificationResult, DomainClassification
from neocortex.domains.router import DomainRouter
from neocortex.permissions.memory_service import InMemoryPermissionService

AGENT_ID = "test_agent"
SCHEMA_NAME = "ncx_shared__technical_knowledge"
DOMAIN_SLUG = "technical_knowledge"


@pytest_asyncio.fixture
async def domain_service() -> InMemoryDomainService:
    svc = InMemoryDomainService()
    await svc.seed_defaults()
    return svc


@pytest.fixture
def permissions() -> InMemoryPermissionService:
    return InMemoryPermissionService(bootstrap_admin_id="admin")


@pytest.fixture
def schema_mgr() -> AsyncMock:
    mgr = AsyncMock()
    # get_graph returns schema info (schema exists)
    mgr.get_graph = AsyncMock(return_value={"schema_name": SCHEMA_NAME})
    mgr.create_graph = AsyncMock(return_value=SCHEMA_NAME)
    return mgr


@pytest.fixture
def classifier() -> AsyncMock:
    mock = AsyncMock(spec=DomainClassifier)
    mock.classify = AsyncMock(
        return_value=ClassificationResult(
            matched_domains=[
                DomainClassification(
                    domain_slug=DOMAIN_SLUG,
                    confidence=0.9,
                    reasoning="technical content",
                )
            ],
        )
    )
    return mock


@pytest.fixture
def router(
    domain_service: InMemoryDomainService,
    classifier: AsyncMock,
    schema_mgr: AsyncMock,
    permissions: InMemoryPermissionService,
) -> DomainRouter:
    return DomainRouter(
        domain_service=domain_service,
        classifier=classifier,
        schema_mgr=schema_mgr,
        permissions=permissions,
    )


@pytest.mark.asyncio
async def test_ensure_schema_grants_permissions_for_existing_schema(
    router: DomainRouter,
    permissions: InMemoryPermissionService,
) -> None:
    """_ensure_schema must grant write permissions even when schema already exists."""
    # Before routing, agent has no permissions
    assert not await permissions.can_write_schema(AGENT_ID, SCHEMA_NAME)

    # Route an episode — this triggers _ensure_schema for existing schema
    results = await router.route_and_extract(
        agent_id=AGENT_ID,
        episode_id=1,
        episode_text="Python async programming patterns",
    )

    # After routing, agent should have write permissions (granted by _ensure_schema)
    assert await permissions.can_write_schema(AGENT_ID, SCHEMA_NAME)
    assert await permissions.can_read_schema(AGENT_ID, SCHEMA_NAME)
    assert len(results) >= 1


@pytest.mark.asyncio
async def test_routing_logs_permission_denial_at_warning(
    domain_service: InMemoryDomainService,
    classifier: AsyncMock,
) -> None:
    """Permission denial must log at WARNING, not DEBUG."""
    from loguru import logger

    # Create a router where _ensure_schema returns a schema name
    # but permissions.can_write_schema always returns False
    permissions_mock = AsyncMock()
    permissions_mock.can_write_schema = AsyncMock(return_value=False)
    permissions_mock.grant = AsyncMock()

    # schema_mgr reports schema doesn't exist so _ensure_schema can't grant
    schema_mgr = AsyncMock()
    schema_mgr.get_graph = AsyncMock(return_value=None)
    schema_mgr.create_graph = AsyncMock(return_value=SCHEMA_NAME)

    router = DomainRouter(
        domain_service=domain_service,
        classifier=classifier,
        schema_mgr=schema_mgr,
        permissions=permissions_mock,
    )

    # Capture loguru output
    captured: list[dict] = []
    sink_id = logger.add(lambda msg: captured.append(msg.record), level="WARNING")
    try:
        results = await router.route_and_extract(
            agent_id=AGENT_ID,
            episode_id=1,
            episode_text="Python async programming patterns",
        )
    finally:
        logger.remove(sink_id)

    # The routing should produce no results because permissions are denied
    assert len(results) == 0

    # Check that a warning-level log was emitted about permission denial
    warning_messages = [r["message"] for r in captured if r["level"].name == "WARNING"]
    assert any("permission_denied" in msg for msg in warning_messages)
