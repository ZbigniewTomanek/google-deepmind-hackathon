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
    created_at: datetime
    updated_at: datetime


class Edge(BaseModel):
    id: int
    source_id: int
    target_id: int
    type_id: int
    weight: float = 1.0
    properties: dict = {}
    created_at: datetime


class Episode(BaseModel):
    id: int
    agent_id: str
    content: str
    embedding: list[float] | None = None
    source_type: str | None = None
    metadata: dict = {}
    created_at: datetime
