from typing import Literal

from pydantic import BaseModel, Field

# --- Tool Outputs ---


class RememberResult(BaseModel):
    status: str
    episode_id: int
    message: str
    extraction_job_id: int | None = None


class GraphContext(BaseModel):
    """Subgraph around a matched node."""

    center_node: dict  # {id, name, type, properties}
    edges: list[dict]  # [{source, target, type, weight, properties}]
    neighbor_nodes: list[dict]  # [{id, name, type}]
    depth: int


class RecallItem(BaseModel):
    item_id: int
    name: str
    content: str
    item_type: str
    score: float = Field(..., description="Hybrid relevance score")
    source: str | None = None
    source_kind: Literal["node", "episode"]
    graph_name: str | None = None
    graph_context: GraphContext | None = None


class RecallResult(BaseModel):
    results: list[RecallItem]
    total: int
    query: str


class TypeInfo(BaseModel):
    id: int
    name: str
    description: str | None = None
    count: int = 0


class GraphStats(BaseModel):
    total_nodes: int
    total_edges: int
    total_episodes: int


class DiscoverResult(BaseModel):
    node_types: list[TypeInfo]
    edge_types: list[TypeInfo]
    stats: GraphStats
    graphs: list[str] = []
