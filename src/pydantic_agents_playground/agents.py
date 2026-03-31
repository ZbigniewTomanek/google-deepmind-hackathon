from collections.abc import Sequence
from time import perf_counter
from typing import Any, cast

from loguru import logger
from pydantic_ai import Agent, RunContext
from pydantic_ai.models.google import GoogleModel
from pydantic_ai.models.test import TestModel

from pydantic_agents_playground.schemas import (
    ExtractedFact,
    ExtractionResult,
    ExtractorAgentDeps,
    LibrarianAgentDeps,
    LibrarianPayload,
    OntologyAgentDeps,
    OntologyClass,
    OntologyProperty,
    OntologyProposal,
    PersistedFact,
    PersistedFactMention,
    SeedMessage,
)

MODEL_NAME = "google-gla:gemini-3-flash-preview"


def build_model(use_test_model: bool):
    if use_test_model:
        logger.info("Using TestModel for agent execution")
        return TestModel()
    logger.info("Using model={}", MODEL_NAME)
    return GoogleModel(MODEL_NAME)


def build_ontology_agent(use_test_model: bool = False) -> Agent[OntologyAgentDeps, OntologyProposal]:
    agent = cast(
        Agent[OntologyAgentDeps, OntologyProposal],
        Agent(
            build_model(use_test_model),
            output_type=OntologyProposal,
            deps_type=OntologyAgentDeps,
            system_prompt=(
                "Propose only reusable concepts.",
                "Extend conservatively and do not remove existing items.",
                "Prefer generic automotive concepts first.",
                "BMW-specific concepts are allowed when useful across this corpus.",
            ),
        ),
    )

    @agent.instructions
    async def ontology_instructions(ctx: RunContext[OntologyAgentDeps]) -> str:
        return "\n".join(
            [
                format_message_block(ctx.deps.message),
                format_classes_block(ctx.deps.existing_classes),
                format_properties_block(ctx.deps.existing_properties),
                "Rules:",
                "- Propose additions or clarifications only.",
                "- Prefer extending with properties before creating new classes.",
                "- Avoid one-off trim, engine-code, or marketing-label classes unless clearly reusable.",
            ]
        )

    return agent


def build_extractor_agent(use_test_model: bool = False) -> Agent[ExtractorAgentDeps, ExtractionResult]:
    agent = cast(
        Agent[ExtractorAgentDeps, ExtractionResult],
        Agent(
            build_model(use_test_model),
            output_type=ExtractionResult,
            deps_type=ExtractorAgentDeps,
            system_prompt=(
                "Every fact must reference a valid property_id.",
                "Use target_entity_id only when value_type='entity'.",
                "Use the message text as the only evidence source.",
                "Do not guess missing numeric values.",
                "Prefer moderately detailed entities and facts when supported by the text.",
            ),
        ),
    )

    @agent.instructions
    async def extractor_instructions(ctx: RunContext[ExtractorAgentDeps]) -> str:
        return "\n".join(
            [
                format_message_block(ctx.deps.message),
                format_classes_block(ctx.deps.classes),
                format_properties_block(ctx.deps.properties),
                "Rules:",
                "- Extract only ontology-aligned entities and facts.",
                "- If a fact cannot fit the ontology, omit it.",
                "- Include a short evidence snippet for every fact.",
            ]
        )

    return agent


def build_librarian_agent(use_test_model: bool = False) -> Agent[LibrarianAgentDeps, LibrarianPayload]:
    agent = cast(
        Agent[LibrarianAgentDeps, LibrarianPayload],
        Agent(
            build_model(use_test_model),
            output_type=LibrarianPayload,
            deps_type=LibrarianAgentDeps,
            system_prompt=(
                "Reject malformed records.",
                "Deduplicate ontology additions.",
                "Deduplicate facts globally using stable fact signatures.",
                "Preserve one provenance row per source message mention.",
                "Keep identifiers stable and machine-friendly.",
            ),
        ),
    )

    @agent.instructions
    async def librarian_instructions(ctx: RunContext[LibrarianAgentDeps]) -> str:
        extracted_entities = (
            "\n".join(
                f"- {entity.entity_id}: {entity.class_id} | {entity.canonical_name}"
                for entity in ctx.deps.extracted_entities
            )
            or "- none"
        )
        extracted_facts = (
            "\n".join(
                f"- {fact.subject_entity_id} | {fact.property_id} | {describe_fact_value(fact)}"
                for fact in ctx.deps.extracted_facts
            )
            or "- none"
        )
        known_entity_ids = "\n".join(f"- {entity_id}" for entity_id in ctx.deps.known_entity_ids) or "- none"
        known_fact_signatures = "\n".join(f"- {signature}" for signature in ctx.deps.known_fact_signatures) or "- none"

        return "\n".join(
            [
                format_message_block(ctx.deps.message),
                format_classes_block(ctx.deps.classes),
                format_properties_block(ctx.deps.properties),
                "Extractor entities:",
                extracted_entities,
                "Extractor facts:",
                extracted_facts,
                "Known entity IDs:",
                known_entity_ids,
                "Known fact signatures:",
                known_fact_signatures,
                "Rules:",
                "- Accept reusable ontology additions only once.",
                "- Reject facts that reference missing entities or missing properties.",
                "- Always fill source_message_id on fact mentions.",
                "- If a fact already exists globally, keep one canonical fact and add only the new mention.",
            ]
        )

    return agent


def format_message_block(message: SeedMessage) -> str:
    return "\n".join(
        [
            "Current message:",
            f"- message_id: {message.message_id}",
            f"- title: {message.title}",
            f"- topic: {message.topic}",
            f"- content: {message.content}",
        ]
    )


def format_classes_block(classes: Sequence[OntologyClass]) -> str:
    items = (
        "\n".join(
            f"- {ontology_class.class_id}: {ontology_class.label} | parent={ontology_class.parent_class_id or 'none'}"
            for ontology_class in classes
        )
        or "- none"
    )
    return "\n".join(["Current ontology classes:", items])


def format_properties_block(properties: Sequence[OntologyProperty]) -> str:
    items = (
        "\n".join(
            (
                f"- {ontology_property.property_id}: {ontology_property.domain_class_id} -> "
                f"{ontology_property.value_type}"
                + (
                    f" ({ontology_property.range_class_id})"
                    if ontology_property.value_type == "entity" and ontology_property.range_class_id
                    else ""
                )
            )
            for ontology_property in properties
        )
        or "- none"
    )
    return "\n".join(["Current ontology properties:", items])


def describe_fact_value(fact: ExtractedFact | PersistedFact | PersistedFactMention) -> str:
    if fact.value_type == "entity":
        return fact.target_entity_id or "missing-target"
    if fact.value_type == "number":
        return str(fact.number_value)
    if fact.value_type == "boolean":
        return str(fact.boolean_value)
    if fact.value_type == "date":
        return fact.date_value or "missing-date"
    return fact.string_value or "missing-string"


def run_stage[AgentDepsT, AgentOutputT](
    agent: Agent[AgentDepsT, AgentOutputT],
    prompt: str,
    deps: AgentDepsT,
    *,
    stage_name: str,
) -> Any:
    logger.info("Starting {} stage", stage_name)
    started_at = perf_counter()
    result = agent.run_sync(prompt, deps=deps)
    logger.info("{} stage finished in {:.2f}s", stage_name, perf_counter() - started_at)
    return result
