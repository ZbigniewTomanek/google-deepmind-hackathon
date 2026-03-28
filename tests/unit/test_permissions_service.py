import pytest
import pytest_asyncio

from neocortex.permissions.memory_service import InMemoryPermissionService

BOOTSTRAP_ADMIN = "admin"
SCHEMA = "ncx_shared__knowledge"
SCHEMA_2 = "ncx_shared__research"


@pytest_asyncio.fixture
async def svc() -> InMemoryPermissionService:
    s = InMemoryPermissionService(bootstrap_admin_id=BOOTSTRAP_ADMIN)
    await s.ensure_admin(BOOTSTRAP_ADMIN)
    return s


@pytest.mark.asyncio
async def test_grant_creates_permission(svc: InMemoryPermissionService) -> None:
    perm = await svc.grant("alice", SCHEMA, can_read=True, can_write=False, granted_by=BOOTSTRAP_ADMIN)
    assert perm.agent_id == "alice"
    assert perm.schema_name == SCHEMA
    assert perm.can_read is True
    assert perm.can_write is False
    assert perm.granted_by == BOOTSTRAP_ADMIN


@pytest.mark.asyncio
async def test_revoke_removes_permission(svc: InMemoryPermissionService) -> None:
    await svc.grant("alice", SCHEMA, can_read=True, can_write=True, granted_by=BOOTSTRAP_ADMIN)
    removed = await svc.revoke("alice", SCHEMA)
    assert removed is True
    assert await svc.can_read_schema("alice", SCHEMA) is False
    assert await svc.can_write_schema("alice", SCHEMA) is False


@pytest.mark.asyncio
async def test_revoke_nonexistent_returns_false(svc: InMemoryPermissionService) -> None:
    assert await svc.revoke("alice", SCHEMA) is False


@pytest.mark.asyncio
async def test_can_read_schema(svc: InMemoryPermissionService) -> None:
    await svc.grant("alice", SCHEMA, can_read=True, can_write=False, granted_by=BOOTSTRAP_ADMIN)
    assert await svc.can_read_schema("alice", SCHEMA) is True
    assert await svc.can_write_schema("alice", SCHEMA) is False


@pytest.mark.asyncio
async def test_can_write_schema(svc: InMemoryPermissionService) -> None:
    await svc.grant("alice", SCHEMA, can_read=False, can_write=True, granted_by=BOOTSTRAP_ADMIN)
    assert await svc.can_write_schema("alice", SCHEMA) is True
    assert await svc.can_read_schema("alice", SCHEMA) is False


@pytest.mark.asyncio
async def test_readable_schemas_returns_correct_subset(svc: InMemoryPermissionService) -> None:
    await svc.grant("alice", SCHEMA, can_read=True, can_write=False, granted_by=BOOTSTRAP_ADMIN)
    await svc.grant("alice", SCHEMA_2, can_read=False, can_write=True, granted_by=BOOTSTRAP_ADMIN)

    readable = await svc.readable_schemas("alice", [SCHEMA, SCHEMA_2, "ncx_shared__other"])
    assert readable == {SCHEMA}


@pytest.mark.asyncio
async def test_readable_schemas_admin_returns_all_candidates(svc: InMemoryPermissionService) -> None:
    candidates = [SCHEMA, SCHEMA_2, "ncx_shared__other"]
    readable = await svc.readable_schemas(BOOTSTRAP_ADMIN, candidates)
    assert readable == set(candidates)


@pytest.mark.asyncio
async def test_readable_schemas_empty_candidates(svc: InMemoryPermissionService) -> None:
    readable = await svc.readable_schemas("alice", [])
    assert readable == set()


@pytest.mark.asyncio
async def test_list_for_agent(svc: InMemoryPermissionService) -> None:
    await svc.grant("alice", SCHEMA, can_read=True, can_write=False, granted_by=BOOTSTRAP_ADMIN)
    await svc.grant("alice", SCHEMA_2, can_read=True, can_write=True, granted_by=BOOTSTRAP_ADMIN)

    perms = await svc.list_for_agent("alice")
    assert len(perms) == 2
    assert perms[0].schema_name == SCHEMA  # sorted by schema_name
    assert perms[1].schema_name == SCHEMA_2


@pytest.mark.asyncio
async def test_list_for_schema(svc: InMemoryPermissionService) -> None:
    await svc.grant("alice", SCHEMA, can_read=True, can_write=False, granted_by=BOOTSTRAP_ADMIN)
    await svc.grant("bob", SCHEMA, can_read=True, can_write=True, granted_by=BOOTSTRAP_ADMIN)

    perms = await svc.list_for_schema(SCHEMA)
    assert len(perms) == 2
    assert perms[0].agent_id == "alice"  # sorted by agent_id
    assert perms[1].agent_id == "bob"


@pytest.mark.asyncio
async def test_admin_bypasses_read_write_checks(svc: InMemoryPermissionService) -> None:
    # Admin has no explicit grant but should bypass checks
    assert await svc.can_read_schema(BOOTSTRAP_ADMIN, SCHEMA) is True
    assert await svc.can_write_schema(BOOTSTRAP_ADMIN, SCHEMA) is True


@pytest.mark.asyncio
async def test_nonexistent_permission_returns_false(svc: InMemoryPermissionService) -> None:
    assert await svc.can_read_schema("unknown_agent", SCHEMA) is False
    assert await svc.can_write_schema("unknown_agent", SCHEMA) is False


@pytest.mark.asyncio
async def test_grant_update_changes_flags(svc: InMemoryPermissionService) -> None:
    await svc.grant("alice", SCHEMA, can_read=False, can_write=False, granted_by=BOOTSTRAP_ADMIN)
    assert await svc.can_read_schema("alice", SCHEMA) is False

    updated = await svc.grant("alice", SCHEMA, can_read=True, can_write=True, granted_by=BOOTSTRAP_ADMIN)
    assert updated.can_read is True
    assert updated.can_write is True
    assert await svc.can_read_schema("alice", SCHEMA) is True


@pytest.mark.asyncio
async def test_set_admin_promotes(svc: InMemoryPermissionService) -> None:
    await svc.set_admin("alice", is_admin=True)
    assert await svc.is_admin("alice") is True


@pytest.mark.asyncio
async def test_set_admin_demotes(svc: InMemoryPermissionService) -> None:
    await svc.set_admin("alice", is_admin=True)
    assert await svc.is_admin("alice") is True
    await svc.set_admin("alice", is_admin=False)
    assert await svc.is_admin("alice") is False


@pytest.mark.asyncio
async def test_set_admin_bootstrap_demotion_raises(svc: InMemoryPermissionService) -> None:
    with pytest.raises(ValueError, match="Cannot demote the bootstrap admin"):
        await svc.set_admin(BOOTSTRAP_ADMIN, is_admin=False)


@pytest.mark.asyncio
async def test_list_agents(svc: InMemoryPermissionService) -> None:
    await svc.set_admin("alice", is_admin=False)
    agents = await svc.list_agents()
    agent_ids = [a.agent_id for a in agents]
    assert BOOTSTRAP_ADMIN in agent_ids
    assert "alice" in agent_ids


@pytest.mark.asyncio
async def test_ensure_admin_idempotent(svc: InMemoryPermissionService) -> None:
    await svc.ensure_admin("alice")
    await svc.ensure_admin("alice")
    assert await svc.is_admin("alice") is True
    agents = await svc.list_agents()
    alice_count = sum(1 for a in agents if a.agent_id == "alice")
    assert alice_count == 1


@pytest.mark.asyncio
async def test_shared_schema_readable_without_grant(svc: InMemoryPermissionService) -> None:
    """Shared schemas are world-readable without explicit grants."""
    svc.register_shared_schema("ncx_shared__user_profile")
    assert await svc.can_read_schema("agent_x", "ncx_shared__user_profile") is True
    # Write still requires explicit grant
    assert await svc.can_write_schema("agent_x", "ncx_shared__user_profile") is False


@pytest.mark.asyncio
async def test_readable_schemas_includes_shared(svc: InMemoryPermissionService) -> None:
    """readable_schemas returns shared schemas even without explicit grants."""
    svc.register_shared_schema("ncx_shared__tech")
    candidates = ["ncx_shared__tech", "ncx_agent1__personal"]
    result = await svc.readable_schemas("agent_x", candidates)
    assert "ncx_shared__tech" in result
    assert "ncx_agent1__personal" not in result
