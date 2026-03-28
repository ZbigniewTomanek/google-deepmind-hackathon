"""Bridge models between LLM output and NeoCortex's data model.

These schemas define what each extraction agent produces and what gets
persisted to the knowledge graph.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

# ── LLM Output Schemas (what agents produce) ──


class ProposedNodeType(BaseModel):
    """Ontology agent proposes new node types."""

    name: str = Field(description="PascalCase type name, e.g. 'Neurotransmitter'")
    description: str = ""


class ProposedEdgeType(BaseModel):
    """Ontology agent proposes new edge types."""

    name: str = Field(description="SCREAMING_SNAKE relationship name, e.g. 'INHIBITS'")
    description: str = ""


class OntologyProposal(BaseModel):
    new_node_types: list[ProposedNodeType] = Field(default_factory=list)
    new_edge_types: list[ProposedEdgeType] = Field(default_factory=list)
    rationale: str = ""


class ExtractedEntity(BaseModel):
    name: str = Field(description="Canonical entity name")
    type_name: str = Field(description="Must match an existing node type name")
    description: str | None = None
    properties: dict = Field(default_factory=dict, description="Scalar facts as key-value pairs")
    importance: float = Field(default=0.5, ge=0.0, le=1.0, description="How critical is this entity to the domain")


class ExtractedRelation(BaseModel):
    source_name: str
    target_name: str
    relation_type: str = Field(description="Must match an existing edge type name")
    weight: float = Field(default=1.0, ge=0.0, le=1.0)
    properties: dict = Field(default_factory=dict, description="Evidence text, confidence, etc.")


class ExtractionResult(BaseModel):
    entities: list[ExtractedEntity] = Field(default_factory=list)
    relations: list[ExtractedRelation] = Field(default_factory=list)
    rationale: str = ""


# ── Librarian Output (deduplicated, ready to persist) ──


class NormalizedEntity(BaseModel):
    """Librarian output — deduplicated, ready to persist."""

    name: str
    type_name: str
    description: str | None = None
    properties: dict = Field(default_factory=dict)
    importance: float = Field(default=0.5, ge=0.0, le=1.0)
    is_new: bool = True  # False if merging with existing


class NormalizedRelation(BaseModel):
    source_name: str
    target_name: str
    relation_type: str
    weight: float = 1.0
    properties: dict = Field(default_factory=dict)


class LibrarianPayload(BaseModel):
    accepted_node_types: list[ProposedNodeType] = Field(default_factory=list)
    accepted_edge_types: list[ProposedEdgeType] = Field(default_factory=list)
    entities: list[NormalizedEntity] = Field(default_factory=list)
    relations: list[NormalizedRelation] = Field(default_factory=list)
    summary: str = ""
