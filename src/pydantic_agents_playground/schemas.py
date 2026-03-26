from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, Field


class SeedMessage(BaseModel):
    message_id: str
    title: str
    topic: str
    content: str


class OntologyClass(BaseModel):
    class_id: str
    label: str
    description: str
    parent_class_id: str | None = None


class OntologyProperty(BaseModel):
    property_id: str
    label: str
    description: str
    domain_class_id: str
    value_type: Literal["string", "number", "boolean", "date", "entity"]
    range_class_id: str | None = None
    multi_valued: bool = False


class OntologyProposal(BaseModel):
    new_classes: list[OntologyClass] = Field(default_factory=list)
    new_properties: list[OntologyProperty] = Field(default_factory=list)
    rationale: str


class ExtractedEntity(BaseModel):
    entity_id: str
    label: str
    class_id: str
    canonical_name: str


class ExtractedFact(BaseModel):
    subject_entity_id: str
    property_id: str
    value_type: Literal["string", "number", "boolean", "date", "entity"]
    string_value: str | None = None
    number_value: float | None = None
    boolean_value: bool | None = None
    date_value: str | None = None
    target_entity_id: str | None = None
    evidence_text: str
    confidence: float


class ExtractionResult(BaseModel):
    entities: list[ExtractedEntity] = Field(default_factory=list)
    facts: list[ExtractedFact] = Field(default_factory=list)
    rationale: str


class PersistedEntity(BaseModel):
    entity_id: str
    label: str
    class_id: str
    canonical_name: str


class PersistedFact(BaseModel):
    subject_entity_id: str
    property_id: str
    value_type: Literal["string", "number", "boolean", "date", "entity"]
    string_value: str | None = None
    number_value: float | None = None
    boolean_value: bool | None = None
    date_value: str | None = None
    target_entity_id: str | None = None


class PersistedFactMention(BaseModel):
    subject_entity_id: str
    property_id: str
    value_type: Literal["string", "number", "boolean", "date", "entity"]
    string_value: str | None = None
    number_value: float | None = None
    boolean_value: bool | None = None
    date_value: str | None = None
    target_entity_id: str | None = None
    source_message_id: str
    evidence_text: str
    confidence: float


class LibrarianPayload(BaseModel):
    accepted_classes: list[OntologyClass] = Field(default_factory=list)
    accepted_properties: list[OntologyProperty] = Field(default_factory=list)
    entities_to_upsert: list[PersistedEntity] = Field(default_factory=list)
    canonical_facts_to_upsert: list[PersistedFact] = Field(default_factory=list)
    fact_mentions_to_insert: list[PersistedFactMention] = Field(default_factory=list)
    summary: str


@dataclass(slots=True)
class OntologyAgentDeps:
    message: SeedMessage
    existing_classes: list[OntologyClass]
    existing_properties: list[OntologyProperty]


@dataclass(slots=True)
class ExtractorAgentDeps:
    message: SeedMessage
    classes: list[OntologyClass]
    properties: list[OntologyProperty]


@dataclass(slots=True)
class LibrarianAgentDeps:
    message: SeedMessage
    classes: list[OntologyClass]
    properties: list[OntologyProperty]
    extracted_entities: list[ExtractedEntity]
    extracted_facts: list[ExtractedFact]
    known_entity_ids: list[str]
    known_fact_signatures: list[str]


class DemoRunSummary(BaseModel):
    db_path: str
    processed_messages: int
    row_counts: dict[str, int] = Field(default_factory=dict)
