"""Auto-provisioning of Auth0 identities into NeoCortex permission system."""

from __future__ import annotations

from loguru import logger

from neocortex.permissions.protocol import PermissionChecker


async def ensure_agent_provisioned(
    permissions: PermissionChecker,
    agent_id: str,
    auth0_permissions: list[str] | None = None,
) -> None:
    """Ensure an Auth0 user is registered and has appropriate permissions.

    Called on first access. Maps Auth0 permissions to NeoCortex roles:
    - "admin:manage" in Auth0 permissions -> is_admin in NeoCortex
    - "memory:write" -> write access to personal graph (automatic via GraphRouter)
    - "memory:read" -> read access (automatic for personal, explicit for shared)

    Personal graph creation is handled by GraphRouter.route_store() on first write,
    so no explicit provisioning needed there.
    """
    agents = await permissions.list_agents()
    existing_ids = {a.agent_id for a in agents}

    if agent_id in existing_ids:
        return  # Already provisioned

    logger.info("auto_provisioning_agent", agent_id=agent_id)

    is_admin = auth0_permissions is not None and "admin:manage" in auth0_permissions
    await permissions.set_admin(agent_id, is_admin=is_admin)
    if is_admin:
        logger.info("agent_promoted_to_admin", agent_id=agent_id)
