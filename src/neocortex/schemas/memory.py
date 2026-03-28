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
    activation_score: float | None = None
    importance: float | None = None
    spreading_bonus: float | None = None
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
    forgotten_nodes: int = 0
    consolidated_episodes: int = 0
    avg_activation: float = 0.0


class DiscoverResult(BaseModel):
    node_types: list[TypeInfo]
    edge_types: list[TypeInfo]
    stats: GraphStats
    graphs: list[str] = []


# --- Granular Discovery Models ---


class DomainInfo(BaseModel):
    slug: str
    name: str
    description: str
    schema_name: str | None = None


class GraphSummary(BaseModel):
    """Discovery-facing graph info (not to be confused with schemas.graph.GraphInfo)."""

    schema_name: str
    is_shared: bool
    purpose: str
    stats: GraphStats


class TypeDetail(BaseModel):
    id: int
    name: str
    description: str | None = None
    count: int = 0
    connected_edge_types: list[str] = []
    sample_names: list[str] = []


class DiscoverDomainsResult(BaseModel):
    domains: list[DomainInfo]
    message: str | None = None


class DiscoverGraphsResult(BaseModel):
    graphs: list[GraphSummary]


class DiscoverOntologyResult(BaseModel):
    graph_name: str
    node_types: list[TypeInfo]
    edge_types: list[TypeInfo]
    stats: GraphStats


class DiscoverDetailsResult(BaseModel):
    graph_name: str
    type_detail: TypeDetail


# --- Node Browsing Models ---


class NodeSummary(BaseModel):
    id: int
    name: str
    type_name: str
    content: str | None = None
    importance: float = 0.5
    access_count: int = 0


class BrowseNodesResult(BaseModel):
    graph_name: str
    type_name: str | None = None
    nodes: list[NodeSummary]
    total: int


class NeighborEdge(BaseModel):
    source_name: str
    source_type: str
    target_name: str
    target_type: str
    edge_type: str
    weight: float = 1.0


class InspectNodeResult(BaseModel):
    graph_name: str
    node: NodeSummary
    edges: list[NeighborEdge]
    neighbor_nodes: list[NodeSummary]
