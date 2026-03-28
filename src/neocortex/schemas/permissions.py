import re
from datetime import datetime

from pydantic import BaseModel, field_validator

_SCHEMA_NAME_PATTERN = re.compile(r"^ncx_[a-z0-9]+__[a-z0-9_]+$")


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

    @field_validator("schema_name")
    @classmethod
    def validate_schema_name(cls, v: str) -> str:
        if not _SCHEMA_NAME_PATTERN.match(v):
            raise ValueError(
                f"Invalid schema name '{v}'. Must match pattern ncx_<owner>__<purpose> "
                "(lowercase alphanumeric with underscores)."
            )
        return v
