from __future__ import annotations

from datetime import UTC, datetime

from neocortex.schemas.permissions import AgentInfo, PermissionInfo


class InMemoryPermissionService:
    """In-memory permission service for testing and mock DB mode."""

    def __init__(self, bootstrap_admin_id: str) -> None:
        self._bootstrap_admin_id = bootstrap_admin_id
        self._permissions: dict[tuple[str, str], PermissionInfo] = {}
        self._agents: dict[str, AgentInfo] = {}
        self._next_perm_id = 1
        self._next_agent_id = 1

    async def is_admin(self, agent_id: str) -> bool:
        agent = self._agents.get(agent_id)
        return agent is not None and agent.is_admin

    async def ensure_admin(self, agent_id: str) -> None:
        if agent_id in self._agents:
            old = self._agents[agent_id]
            self._agents[agent_id] = old.model_copy(update={"is_admin": True, "updated_at": datetime.now(UTC)})
        else:
            now = datetime.now(UTC)
            self._agents[agent_id] = AgentInfo(
                id=self._next_agent_id,
                agent_id=agent_id,
                is_admin=True,
                created_at=now,
                updated_at=now,
            )
            self._next_agent_id += 1

    async def can_read_schema(self, agent_id: str, schema_name: str) -> bool:
        if await self.is_admin(agent_id):
            return True
        perm = self._permissions.get((agent_id, schema_name))
        return perm is not None and perm.can_read

    async def can_write_schema(self, agent_id: str, schema_name: str) -> bool:
        if await self.is_admin(agent_id):
            return True
        perm = self._permissions.get((agent_id, schema_name))
        return perm is not None and perm.can_write

    async def readable_schemas(self, agent_id: str, candidates: list[str]) -> set[str]:
        if not candidates:
            return set()
        if await self.is_admin(agent_id):
            return set(candidates)
        return {
            schema
            for schema in candidates
            if (perm := self._permissions.get((agent_id, schema))) is not None and perm.can_read
        }

    async def grant(
        self,
        agent_id: str,
        schema_name: str,
        can_read: bool,
        can_write: bool,
        granted_by: str,
    ) -> PermissionInfo:
        now = datetime.now(UTC)
        key = (agent_id, schema_name)
        existing = self._permissions.get(key)
        if existing is not None:
            updated = existing.model_copy(
                update={
                    "can_read": can_read,
                    "can_write": can_write,
                    "granted_by": granted_by,
                    "updated_at": now,
                }
            )
            self._permissions[key] = updated
            return updated
        perm = PermissionInfo(
            id=self._next_perm_id,
            agent_id=agent_id,
            schema_name=schema_name,
            can_read=can_read,
            can_write=can_write,
            granted_by=granted_by,
            created_at=now,
            updated_at=now,
        )
        self._next_perm_id += 1
        self._permissions[key] = perm
        return perm

    async def revoke(self, agent_id: str, schema_name: str) -> bool:
        key = (agent_id, schema_name)
        if key in self._permissions:
            del self._permissions[key]
            return True
        return False

    async def list_for_agent(self, agent_id: str) -> list[PermissionInfo]:
        return sorted(
            [p for p in self._permissions.values() if p.agent_id == agent_id],
            key=lambda p: p.schema_name,
        )

    async def list_for_schema(self, schema_name: str) -> list[PermissionInfo]:
        return sorted(
            [p for p in self._permissions.values() if p.schema_name == schema_name],
            key=lambda p: p.agent_id,
        )

    async def set_admin(self, agent_id: str, is_admin: bool) -> None:
        if agent_id == self._bootstrap_admin_id and not is_admin:
            raise ValueError(f"Cannot demote the bootstrap admin '{self._bootstrap_admin_id}'")
        now = datetime.now(UTC)
        if agent_id in self._agents:
            old = self._agents[agent_id]
            self._agents[agent_id] = old.model_copy(update={"is_admin": is_admin, "updated_at": now})
        else:
            self._agents[agent_id] = AgentInfo(
                id=self._next_agent_id,
                agent_id=agent_id,
                is_admin=is_admin,
                created_at=now,
                updated_at=now,
            )
            self._next_agent_id += 1

    async def list_agents(self) -> list[AgentInfo]:
        return sorted(self._agents.values(), key=lambda a: a.agent_id)
