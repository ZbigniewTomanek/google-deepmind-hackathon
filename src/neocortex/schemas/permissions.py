from datetime import datetime

from pydantic import BaseModel


class AgentInfo(BaseModel):
    id: int
    agent_id: str
    is_admin: bool
    created_at: datetime
    updated_at: datetime


class PermissionInfo(BaseModel):
    id: int
    agent_id: str
    schema_name: str
    can_read: bool
    can_write: bool
    granted_by: str
    created_at: datetime
    updated_at: datetime


class PermissionGrant(BaseModel):
    """Request body for granting/updating permissions."""

    agent_id: str
    schema_name: str
    can_read: bool = False
    can_write: bool = False
