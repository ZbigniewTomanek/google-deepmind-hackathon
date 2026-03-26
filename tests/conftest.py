import pytest_asyncio

from neocortex.config import PostgresConfig
from neocortex.graph_service import GraphService
from neocortex.postgres_service import PostgresService


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def pg_service():
    """Session-scoped PostgresService connected to the Docker PostgreSQL."""
    config = PostgresConfig()
    service = PostgresService(config)
    await service.connect()
    yield service
    await service.disconnect()


@pytest_asyncio.fixture(loop_scope="session")
async def graph_service(pg_service):
    """Per-test GraphService. Cleans up created test data after each test.

    IMPORTANT: All test data must follow naming conventions for cleanup:
    - Nodes: use source="test_<something>"
    - Episodes: use agent_id="test_<something>"
    - Node types: use name="Test_<Something>"
    - Edge types: use name="TEST_<SOMETHING>"
    """
    gs = GraphService(pg_service)
    yield gs
    # Cleanup: remove test data (edges cascade from nodes via ON DELETE CASCADE)
    await pg_service.execute("DELETE FROM episode WHERE agent_id LIKE 'test_%'")
    await pg_service.execute("DELETE FROM node WHERE source LIKE 'test_%'")
    await pg_service.execute("DELETE FROM node_type WHERE name LIKE 'Test_%'")
    await pg_service.execute("DELETE FROM edge_type WHERE name LIKE 'TEST_%'")
