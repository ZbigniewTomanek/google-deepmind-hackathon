import sys
from pathlib import Path

import pytest

from neocortex.db.mock import InMemoryRepository
from neocortex.mcp_settings import MCPSettings
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
def test_server(test_settings: MCPSettings):
    return create_server(test_settings)
