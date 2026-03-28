from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class SemanticDomain(BaseModel):
    """A semantic domain in the upper ontology."""

    id: int | None = None
    slug: str
    name: str
    description: str
    schema_name: str | None = None
    seed: bool = False
    created_at: datetime | None = None
    created_by: str | None = None


class DomainClassification(BaseModel):
    """A single domain match from the classifier."""

    domain_slug: str
    confidence: float = Field(ge=0, le=1)
    reasoning: str


class ProposedDomain(BaseModel):
    """A new domain proposal from the classifier."""

    slug: str
    name: str
    description: str
    reasoning: str


class ClassificationResult(BaseModel):
    """Full classification output from the domain classifier."""

    matched_domains: list[DomainClassification] = []
    proposed_domain: ProposedDomain | None = None


class RoutingResult(BaseModel):
    """Result of routing an episode to a shared schema."""

    domain_slug: str
    schema_name: str
    confidence: float
    extraction_job_id: int | None = None
