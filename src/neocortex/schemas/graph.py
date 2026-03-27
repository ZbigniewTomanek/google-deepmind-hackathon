from datetime import datetime

from pydantic import BaseModel


class GraphInfo(BaseModel):
    id: int
    agent_id: str
    purpose: str
    schema_name: str
    is_shared: bool
    created_at: datetime
