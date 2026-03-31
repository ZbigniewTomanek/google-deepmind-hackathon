# Stage 1: Domain Routing Permission Fix

**Goal**: Fix `_ensure_schema()` to grant write permissions when finding an existing schema, unblocking domain routing for all agents.
**Dependencies**: None

---

## Background

`_ensure_schema()` in `src/neocortex/domains/router.py:188-214` has two code paths:

1. **Schema exists** (line 194): returns `domain.schema_name` -- NO permissions granted
2. **Schema needs creation** (line 203): creates schema AND grants read+write permissions

Shared schemas are pre-provisioned at startup by `services.py:114`. Every subsequent routing call hits path #1 and silently fails the permission check at line 122.

---

## Steps

### 1. Fix `_ensure_schema()` in `router.py`

**File**: `src/neocortex/domains/router.py:188-214`

After finding an existing schema (line 194), add a permission grant before returning:

```python
async def _ensure_schema(self, domain: SemanticDomain, agent_id: str) -> str | None:
    if domain.schema_name is not None:
        if self._schema_mgr is not None:
            existing = await self._schema_mgr.get_graph(agent_id="shared", purpose=domain.slug)
            if existing is not None:
                # Grant permissions for this agent (idempotent)
                await self._permissions.grant(
                    agent_id=agent_id,
                    schema_name=domain.schema_name,
                    can_read=True,
                    can_write=True,
                    granted_by="domain_router",
                )
                return domain.schema_name
        else:
            return domain.schema_name
    # ... rest unchanged ...
```

The `grant()` method must be idempotent (ON CONFLICT DO UPDATE or similar). Verify this in the PostgresPermissionService implementation.

### 2. Add INFO-level logging for permission grant

**File**: `src/neocortex/domains/router.py`

After the grant call, add:

```python
logger.info(
    "domain_schema_permission_granted",
    agent_id=agent_id,
    schema_name=domain.schema_name,
    domain_slug=domain.slug,
)
```

### 3. Upgrade permission denial log from DEBUG to WARNING

**File**: `src/neocortex/domains/router.py:124`

Change `logger.debug` to `logger.warning` so permission denials are visible in default logs:

```python
logger.warning(
    "domain_routing_permission_denied",
    agent_id=agent_id,
    schema_name=schema_name,
    domain_slug=match.domain_slug,
)
```

### 4. Verify `grant()` is idempotent

**File**: `src/neocortex/permissions/pg_service.py`

Read the `grant()` method and confirm it uses `ON CONFLICT DO UPDATE` or equivalent. If not, add upsert semantics so repeated grants don't raise errors.

---

## Verification

```bash
# All existing tests pass
uv run pytest tests/ -v -x

# Specifically check domain routing tests
uv run pytest tests/ -v -k "domain" -x
```

Expected: No test failures. The permission grant is additive (grants that already exist are no-ops).

---

## Commit

```
fix(routing): grant write permissions in _ensure_schema for existing shared schemas

_ensure_schema() only granted permissions when creating new schemas,
not when finding pre-provisioned ones. This caused all domain routing
to silently fail (classification succeeded but can_write_schema blocked).

Fixes M5 (0/28 domain routing) from Plan 18.5 E2E revalidation.
```
