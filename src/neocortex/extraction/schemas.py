"""Bridge models between LLM output and NeoCortex's data model.

These schemas define what each extraction agent produces and what gets
persisted to the knowledge graph.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator, model_validator

# ── LLM Output Schemas (what agents produce) ──


class ProposedNodeType(BaseModel):
    """Ontology agent proposes new node types."""

    name: str = Field(description="PascalCase type name, e.g. 'Neurotransmitter'")
    description: str = ""

    @field_validator("name")
    @classmethod
    def validate_type_name(cls, v: str) -> str:
        v = v.strip()
        if len(v) > 60:
            raise ValueError(f"Type name too long ({len(v)} chars)")
        if v and not v[0].isupper():
            raise ValueError(f"Type name must start with uppercase: '{v}'")
        return v


class ProposedEdgeType(BaseModel):
    """Ontology agent proposes new edge types."""

    name: str = Field(description="SCREAMING_SNAKE relationship name, e.g. 'INHIBITS'")
    description: str = ""

    @field_validator("name")
    @classmethod
    def validate_type_name(cls, v: str) -> str:
        v = v.strip()
        if len(v) > 60:
            raise ValueError(f"Type name too long ({len(v)} chars)")
        if v and not v[0].isupper():
            raise ValueError(f"Type name must start with uppercase: '{v}'")
        return v


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
    supersedes: str | None = Field(
        default=None,
        description="If this entity CORRECTS or SUPERSEDES an existing entity, "
        "put the name of the old entity here. Signals: 'CORRECTION', 'UPDATE', "
        "'instead of', 'replaced by', 'switched from', 'no longer'.",
    )
    temporal_signal: str | None = Field(
        default=None,
        description="The type of temporal relationship: 'CORRECTS' (error fix) "
        "or 'SUPERSEDES' (newer version, reversed decision). "
        "Only set when 'supersedes' is also set.",
    )

    @field_validator("type_name")
    @classmethod
    def validate_type_name(cls, v: str) -> str:
        v = v.strip()
        if len(v) > 60:
            raise ValueError(f"Type name too long ({len(v)} chars)")
        if v and not v[0].isupper():
            raise ValueError(f"Type name must start with uppercase: '{v}'")
        return v


class ExtractedRelation(BaseModel):
    source_name: str
    target_name: str
    relation_type: str = Field(
        description="Must match an existing edge type name. "
        "Use 'CORRECTS' or 'SUPERSEDES' for temporal correction relationships."
    )
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


# ── Tool-driven curation output (Stage 3, Plan 16) ──


class CurationAction(BaseModel):
    """A single action taken by the librarian during graph curation."""

    action: str  # "created_node", "updated_node", "archived_node", "created_edge", "removed_edge"
    entity_name: str | None = None
    edge_source: str | None = None
    edge_target: str | None = None
    details: str = ""


class CurationSummary(BaseModel):
    """Summary of all curation actions taken by the librarian.

    This replaces LibrarianPayload — the librarian now executes changes
    via tools and reports what it did, rather than producing a payload
    for blind persistence.

    Counts are computed from the actions list via validator — the LLM
    only needs to populate `actions` and `summary`, not track counts.
    """

    actions: list[CurationAction] = Field(default_factory=list)
    summary: str = ""
    entities_created: int = 0
    entities_updated: int = 0
    entities_archived: int = 0
    edges_created: int = 0
    edges_removed: int = 0

    @model_validator(mode="after")
    def _recompute_counts(self) -> CurationSummary:
        """Derive counts from the actions list so LLM doesn't need to count."""
        self.entities_created = sum(1 for a in self.actions if a.action == "created_node")
        self.entities_updated = sum(1 for a in self.actions if a.action == "updated_node")
        self.entities_archived = sum(1 for a in self.actions if a.action == "archived_node")
        self.edges_created = sum(1 for a in self.actions if a.action == "created_edge")
        self.edges_removed = sum(1 for a in self.actions if a.action == "removed_edge")
        return self
