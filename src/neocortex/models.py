from datetime import datetime

from pydantic import BaseModel


class NodeType(BaseModel):
    id: int
    name: str
    description: str | None = None
    created_at: datetime


class EdgeType(BaseModel):
    id: int
    name: str
    description: str | None = None
    created_at: datetime


class Node(BaseModel):
    id: int
    type_id: int
    name: str
    content: str | None = None
    properties: dict = {}
    embedding: list[float] | None = None
    source: str | None = None
    access_count: int = 0
    last_accessed_at: datetime | None = None
    importance: float = 0.5
    forgotten: bool = False
    forgotten_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class Edge(BaseModel):
    id: int
    source_id: int
    target_id: int
    type_id: int
    weight: float = 1.0
    properties: dict = {}
    last_reinforced_at: datetime | None = None
    created_at: datetime


class Episode(BaseModel):
    id: int
    agent_id: str
    content: str
    embedding: list[float] | None = None
    source_type: str | None = None
    metadata: dict = {}
    access_count: int = 0
    last_accessed_at: datetime | None = None
    importance: float = 0.5
    consolidated: bool = False
    content_hash: str | None = None
    session_id: str | None = None
    session_sequence: int | None = None
    created_at: datetime
