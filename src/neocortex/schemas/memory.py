from pydantic import BaseModel, Field

# --- Tool Outputs ---


class RememberResult(BaseModel):
    status: str
    episode_id: int
    message: str


class RecallItem(BaseModel):
    node_id: int
    name: str
    content: str
    node_type: str
    score: float = Field(..., description="Hybrid relevance score")
    source: str | None = None


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
