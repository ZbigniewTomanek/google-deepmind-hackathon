from __future__ import annotations

from typing import Protocol

from neocortex.schemas.permissions import AgentInfo, PermissionInfo


class PermissionChecker(Protocol):
    async def is_admin(self, agent_id: str) -> bool: ...

    async def ensure_admin(self, agent_id: str) -> None:
        """Register agent as admin in agent_registry."""

    async def can_read_schema(self, agent_id: str, schema_name: str) -> bool: ...

    async def can_write_schema(self, agent_id: str, schema_name: str) -> bool: ...

    async def readable_schemas(self, agent_id: str, candidates: list[str]) -> set[str]:
        """Return the subset of candidate schema names the agent can read.

        Batch method to avoid N+1 queries in route_recall/route_discover.
        Admins return all candidates.
        """

    async def grant(
        self,
        agent_id: str,
        schema_name: str,
        can_read: bool,
        can_write: bool,
        granted_by: str,
    ) -> PermissionInfo: ...

    async def revoke(self, agent_id: str, schema_name: str) -> bool: ...

    async def list_for_agent(self, agent_id: str) -> list[PermissionInfo]: ...

    async def list_for_schema(self, schema_name: str) -> list[PermissionInfo]: ...

    async def set_admin(self, agent_id: str, is_admin: bool) -> None:
        """Promote or demote an agent. Upserts into agent_registry.

        Raises ValueError if attempting to demote the bootstrap admin.
        """

    async def list_agents(self) -> list[AgentInfo]: ...
