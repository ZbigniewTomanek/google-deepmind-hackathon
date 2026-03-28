import sys
from pathlib import Path

import pytest
import pytest_asyncio

from neocortex.db.mock import InMemoryRepository
from neocortex.graph_router import GraphRouter
from neocortex.mcp_settings import MCPSettings
from neocortex.permissions.memory_service import InMemoryPermissionService
from neocortex.schema_manager import SchemaManager
from neocortex.server import create_server

TESTS_DIR = Path(__file__).resolve().parents[1]
sys.path[:] = [entry for entry in sys.path if Path(entry or ".").resolve() != TESTS_DIR]


@pytest.fixture
def mock_repo() -> InMemoryRepository:
    return InMemoryRepository()


@pytest.fixture
def test_settings() -> MCPSettings:
    return MCPSettings(auth_mode="none", mock_db=True)


@pytest.fixture
def test_settings_no_domains() -> MCPSettings:
    return MCPSettings(auth_mode="none", mock_db=True, domain_routing_enabled=False)


@pytest.fixture
def test_server(test_settings: MCPSettings):
    return create_server(test_settings)


@pytest.fixture
def test_server_no_domains(test_settings_no_domains: MCPSettings):
    return create_server(test_settings_no_domains)


@pytest_asyncio.fixture
async def schema_manager(pg_service) -> SchemaManager:
    return SchemaManager(pg_service)


@pytest_asyncio.fixture
async def graph_router(schema_manager: SchemaManager, pg_service) -> GraphRouter:
    permissions = InMemoryPermissionService(bootstrap_admin_id="admin")
    await permissions.ensure_admin("admin")
    return GraphRouter(schema_manager, pg_service.pool, permissions=permissions)
