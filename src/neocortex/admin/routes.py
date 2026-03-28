from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from neocortex.admin.auth import require_admin
from neocortex.schemas.permissions import PermissionGrant, PermissionInfo

router = APIRouter(prefix="/admin", tags=["admin"])


# ---------------------------------------------------------------------------
# Permission management
# ---------------------------------------------------------------------------


@router.post("/permissions", response_model=PermissionInfo)
async def grant_permission(
    body: PermissionGrant,
    request: Request,
    admin_id: Annotated[str, Depends(require_admin)],
) -> PermissionInfo:
    permissions = request.app.state.permissions
    return await permissions.grant(
        agent_id=body.agent_id,
        schema_name=body.schema_name,
        can_read=body.can_read,
        can_write=body.can_write,
        granted_by=admin_id,
    )


@router.delete("/permissions/{agent_id}/{schema_name}")
async def revoke_permission(
    agent_id: str,
    schema_name: str,
    request: Request,
    admin_id: Annotated[str, Depends(require_admin)],
):
    permissions = request.app.state.permissions
    removed = await permissions.revoke(agent_id, schema_name)
    if not removed:
        raise HTTPException(status_code=404, detail="Permission not found")
    return {"status": "revoked", "agent_id": agent_id, "schema_name": schema_name}


@router.get("/permissions", response_model=list[PermissionInfo])
async def list_permissions(
    request: Request,
    admin_id: Annotated[str, Depends(require_admin)],
    agent_id: str | None = None,
    schema_name: str | None = None,
) -> list[PermissionInfo]:
    permissions = request.app.state.permissions
    if agent_id:
        return await permissions.list_for_agent(agent_id)
    if schema_name:
        return await permissions.list_for_schema(schema_name)
    return await permissions.list_all_permissions()


@router.get("/permissions/{agent_id}", response_model=list[PermissionInfo])
async def list_permissions_for_agent(
    agent_id: str,
    request: Request,
    admin_id: Annotated[str, Depends(require_admin)],
) -> list[PermissionInfo]:
    permissions = request.app.state.permissions
    return await permissions.list_for_agent(agent_id)


# ---------------------------------------------------------------------------
# Agent management
# ---------------------------------------------------------------------------


class AdminStatusRequest(BaseModel):
    is_admin: bool


@router.get("/agents")
async def list_agents(
    request: Request,
    admin_id: Annotated[str, Depends(require_admin)],
):
    permissions = request.app.state.permissions
    return await permissions.list_agents()


@router.put("/agents/{agent_id}/admin")
async def promote_agent(
    agent_id: str,
    body: AdminStatusRequest,
    request: Request,
    admin_id: Annotated[str, Depends(require_admin)],
):
    permissions = request.app.state.permissions
    try:
        await permissions.set_admin(agent_id, is_admin=body.is_admin)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    status = "promoted" if body.is_admin else "demoted"
    return {"status": status, "agent_id": agent_id}


@router.delete("/agents/{agent_id}/admin")
async def demote_agent(
    agent_id: str,
    request: Request,
    admin_id: Annotated[str, Depends(require_admin)],
):
    permissions = request.app.state.permissions
    try:
        await permissions.set_admin(agent_id, is_admin=False)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "demoted", "agent_id": agent_id}


# ---------------------------------------------------------------------------
# Graph management
# ---------------------------------------------------------------------------


class CreateGraphRequest(BaseModel):
    purpose: str


@router.post("/graphs")
async def create_graph(
    body: CreateGraphRequest,
    request: Request,
    admin_id: Annotated[str, Depends(require_admin)],
):
    schema_mgr = getattr(request.app.state, "schema_mgr", None)
    if schema_mgr is None:
        raise HTTPException(status_code=501, detail="Graph management requires a real database")
    schema_name = await schema_mgr.create_graph("shared", body.purpose, is_shared=True)
    return {"schema_name": schema_name, "purpose": body.purpose}


@router.get("/graphs")
async def list_graphs(
    request: Request,
    admin_id: Annotated[str, Depends(require_admin)],
):
    schema_mgr = getattr(request.app.state, "schema_mgr", None)
    if schema_mgr is None:
        raise HTTPException(status_code=501, detail="Graph management requires a real database")
    graphs = await schema_mgr.list_graphs()
    return graphs


@router.delete("/graphs/{schema_name}")
async def drop_graph(
    schema_name: str,
    request: Request,
    admin_id: Annotated[str, Depends(require_admin)],
):
    schema_mgr = getattr(request.app.state, "schema_mgr", None)
    if schema_mgr is None:
        raise HTTPException(status_code=501, detail="Graph management requires a real database")
    deleted = await schema_mgr.drop_graph(schema_name)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Graph '{schema_name}' not found")
    return {"status": "dropped", "schema_name": schema_name}
