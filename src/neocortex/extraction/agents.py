"""Three-agent extraction pipeline: ontology, extractor, librarian.

Each agent is built via a factory function that accepts an inference config.
Agents are domain-agnostic — they work with any text, not just medical content.
"""

from __future__ import annotations

from dataclasses import dataclass

from loguru import logger
from pydantic_ai import Agent, RunContext
from pydantic_ai.models.google import GoogleModel
from pydantic_ai.models.test import TestModel
from pydantic_ai.settings import ModelSettings, ThinkingLevel

from neocortex.extraction.schemas import (
    ExtractedEntity,
    ExtractedRelation,
    ExtractionResult,
    LibrarianPayload,
    OntologyProposal,
)

DEFAULT_MODEL_NAME = "gemini-3-flash-preview"
DEFAULT_THINKING_EFFORT = "low"


@dataclass
class AgentInferenceConfig:
    """Per-agent inference configuration (model, thinking budget, etc.)."""

    model_name: str = DEFAULT_MODEL_NAME
    thinking_effort: ThinkingLevel | None = DEFAULT_THINKING_EFFORT
    use_test_model: bool = False

    @property
    def model_settings(self) -> ModelSettings | None:
        """Build pydantic-ai model_settings dict for agent.run()."""
        if self.thinking_effort is not None:
            return ModelSettings(thinking=self.thinking_effort)
        return None


def _build_model(config: AgentInferenceConfig):
    """Build the LLM model from inference config."""
    if config.use_test_model:
        logger.debug("Using TestModel for extraction agents")
        return TestModel()
    logger.debug("Using GoogleModel model_name={}", config.model_name)
    return GoogleModel(config.model_name)


# ── Ontology Agent ──


@dataclass
class OntologyAgentDeps:
    episode_text: str
    existing_node_types: list[str]  # names only
    existing_edge_types: list[str]


def build_ontology_agent(
    config: AgentInferenceConfig | None = None,
) -> Agent[OntologyAgentDeps, OntologyProposal]:
    cfg = config or AgentInferenceConfig()
    model = _build_model(cfg)
    agent = Agent(
        model,
        output_type=OntologyProposal,
        deps_type=OntologyAgentDeps,
        system_prompt=(
            "You are an ontology engineer. Given a text passage, propose new node types "
            "and edge types that would be needed to represent the knowledge in the text.",
            "Propose only reusable, general concepts — not instance-level names.",
            "Extend conservatively: prefer existing types when possible.",
            "Node type names: PascalCase (e.g. Drug, Neurotransmitter, Disease).",
            "Edge type names: SCREAMING_SNAKE (e.g. TREATS, INHIBITS, CAUSES).",
        ),
    )

    @agent.instructions
    async def inject_context(ctx: RunContext[OntologyAgentDeps]) -> str:
        existing_nt = "\n".join(f"- {n}" for n in ctx.deps.existing_node_types) or "- none"
        existing_et = "\n".join(f"- {n}" for n in ctx.deps.existing_edge_types) or "- none"
        return "\n".join(
            [
                "Text to analyze:",
                ctx.deps.episode_text,
                "",
                "Existing node types:",
                existing_nt,
                "",
                "Existing edge types:",
                existing_et,
                "",
                "Rules:",
                "- Propose additions only — do not remove existing types.",
                "- Prefer extending with new edge types before creating new node types.",
                "- Avoid one-off or overly specific types.",
            ]
        )

    return agent  # ty: ignore[invalid-return-type]


# ── Extractor Agent ──


@dataclass
class ExtractorAgentDeps:
    episode_text: str
    node_types: list[str]
    edge_types: list[str]


def build_extractor_agent(
    config: AgentInferenceConfig | None = None,
) -> Agent[ExtractorAgentDeps, ExtractionResult]:
    cfg = config or AgentInferenceConfig()
    model = _build_model(cfg)
    agent = Agent(
        model,
        output_type=ExtractionResult,
        deps_type=ExtractorAgentDeps,
        system_prompt=(
            "You are a knowledge extraction specialist. Extract entities and relations "
            "from the given text, aligned to the provided ontology types.",
            "Every entity must use an existing node type name.",
            "Every relation must use an existing edge type name.",
            "Use the text as the only evidence source — do not invent facts.",
            "Prefer canonical, normalized names for entities.",
        ),
    )

    @agent.instructions
    async def inject_context(ctx: RunContext[ExtractorAgentDeps]) -> str:
        nt_list = "\n".join(f"- {n}" for n in ctx.deps.node_types) or "- none"
        et_list = "\n".join(f"- {n}" for n in ctx.deps.edge_types) or "- none"
        return "\n".join(
            [
                "Text to extract from:",
                ctx.deps.episode_text,
                "",
                "Available node types:",
                nt_list,
                "",
                "Available edge types:",
                et_list,
                "",
                "Rules:",
                "- Extract only ontology-aligned entities and relations.",
                "- If a relation cannot fit the ontology, omit it.",
                "- Include evidence text in relation properties when possible.",
            ]
        )

    return agent  # ty: ignore[invalid-return-type]


# ── Librarian Agent ──


@dataclass
class LibrarianAgentDeps:
    episode_text: str
    node_types: list[str]
    edge_types: list[str]
    extracted_entities: list[ExtractedEntity]
    extracted_relations: list[ExtractedRelation]
    known_node_names: list[str]  # for dedup


def build_librarian_agent(
    config: AgentInferenceConfig | None = None,
) -> Agent[LibrarianAgentDeps, LibrarianPayload]:
    cfg = config or AgentInferenceConfig()
    model = _build_model(cfg)
    agent = Agent(
        model,
        output_type=LibrarianPayload,
        deps_type=LibrarianAgentDeps,
        system_prompt=(
            "You are a knowledge graph librarian. Your job is to normalize, deduplicate, "
            "and validate extracted entities and relations before they are persisted.",
            "Reject malformed records.",
            "Deduplicate entities against the known node list.",
            "Normalize entity names to canonical forms.",
            "Keep identifiers stable and machine-friendly.",
        ),
    )

    @agent.instructions
    async def inject_context(ctx: RunContext[LibrarianAgentDeps]) -> str:
        entities_str = (
            "\n".join(
                f"- {e.name} [{e.type_name}]: {e.description or 'no description'}" for e in ctx.deps.extracted_entities
            )
            or "- none"
        )
        relations_str = (
            "\n".join(
                f"- {r.source_name} --[{r.relation_type}]--> {r.target_name}" for r in ctx.deps.extracted_relations
            )
            or "- none"
        )
        known_str = "\n".join(f"- {n}" for n in ctx.deps.known_node_names) or "- none"
        return "\n".join(
            [
                "Source text:",
                ctx.deps.episode_text,
                "",
                "Available node types:",
                "\n".join(f"- {n}" for n in ctx.deps.node_types) or "- none",
                "",
                "Available edge types:",
                "\n".join(f"- {n}" for n in ctx.deps.edge_types) or "- none",
                "",
                "Extracted entities:",
                entities_str,
                "",
                "Extracted relations:",
                relations_str,
                "",
                "Known node names (for deduplication):",
                known_str,
                "",
                "Rules:",
                "- Accept reusable ontology additions only.",
                "- Reject relations that reference missing entities or types.",
                "- Mark entities as is_new=False if they match a known node name.",
                "- Normalize names to canonical form (proper casing, full names).",
            ]
        )

    return agent  # ty: ignore[invalid-return-type]
