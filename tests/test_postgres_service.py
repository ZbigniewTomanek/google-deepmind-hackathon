import pytest


@pytest.mark.asyncio
async def test_health_check(pg_service):
    health = await pg_service.health_check()
    assert health["status"] == "healthy"
    assert "vector" in health["extensions"]
    assert "pg_trgm" in health["extensions"]
    assert health["database"] == "neocortex"


@pytest.mark.asyncio
async def test_fetchval(pg_service):
    result = await pg_service.fetchval("SELECT 1 + 1")
    assert result == 2
