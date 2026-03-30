"""Three-agent extraction pipeline: ontology, extractor, librarian.

Each agent is built via a factory function that accepts an inference config.
Agents are domain-agnostic — they work with any text, not just medical content.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from loguru import logger
from pydantic_ai import Agent, RunContext
from pydantic_ai.models.google import GoogleModel
from pydantic_ai.models.test import TestModel
from pydantic_ai.settings import ModelSettings, ThinkingLevel

if TYPE_CHECKING:
    from neocortex.db.protocol import MemoryRepository
    from neocortex.embedding_service import EmbeddingService

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
    node_type_descriptions: dict[str, str] | None = None  # {type_name: description}
    edge_type_descriptions: dict[str, str] | None = None
    domain_hint: str | None = None  # e.g. "Technical Knowledge: Programming languages, ..."


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
        parts: list[str] = []
        if ctx.deps.domain_hint:
            parts.extend(
                [
                    f"Domain context: {ctx.deps.domain_hint}",
                    "Propose types that are semantically appropriate for this domain.",
                    "Do NOT reuse types from unrelated domains even if they exist.",
                    "",
                ]
            )
        nt_descs = ctx.deps.node_type_descriptions or {}
        et_descs = ctx.deps.edge_type_descriptions or {}
        existing_nt = (
            "\n".join(f"- {n}: {nt_descs[n]}" if nt_descs.get(n) else f"- {n}" for n in ctx.deps.existing_node_types)
            or "- none"
        )
        existing_et = (
            "\n".join(f"- {n}: {et_descs[n]}" if et_descs.get(n) else f"- {n}" for n in ctx.deps.existing_edge_types)
            or "- none"
        )
        parts.extend(
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
        return "\n".join(parts)

    return agent  # ty: ignore[invalid-return-type]


# ── Extractor Agent ──


@dataclass
class ExtractorAgentDeps:
    episode_text: str
    node_types: list[str]
    edge_types: list[str]
    node_type_descriptions: dict[str, str] | None = None
    edge_type_descriptions: dict[str, str] | None = None
    domain_hint: str | None = None


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
            "Assign an importance score (0.0-1.0) to each entity:\n"
            "  0.0-0.3: Peripheral, contextual detail\n"
            "  0.3-0.6: Standard factual entity\n"
            "  0.6-0.8: Central concept referenced multiple times\n"
            "  0.8-1.0: Critical domain entity (core drug, disease, mechanism)",
        ),
    )

    @agent.instructions
    async def inject_context(ctx: RunContext[ExtractorAgentDeps]) -> str:
        parts: list[str] = []
        if ctx.deps.domain_hint:
            parts.extend(
                [
                    f"Domain context: {ctx.deps.domain_hint}",
                    "Extract entities and relations appropriate for this domain.",
                    "",
                ]
            )
        nt_descs = ctx.deps.node_type_descriptions or {}
        et_descs = ctx.deps.edge_type_descriptions or {}
        nt_list = (
            "\n".join(f"- {n}: {nt_descs[n]}" if nt_descs.get(n) else f"- {n}" for n in ctx.deps.node_types) or "- none"
        )
        et_list = (
            "\n".join(f"- {n}: {et_descs[n]}" if et_descs.get(n) else f"- {n}" for n in ctx.deps.edge_types) or "- none"
        )
        parts.extend(
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
        return "\n".join(parts)

    return agent  # ty: ignore[invalid-return-type]


# ── Librarian Agent ──


@dataclass
class LibrarianAgentDeps:
    episode_text: str
    node_types: list[str]
    edge_types: list[str]
    extracted_entities: list[ExtractedEntity]
    extracted_relations: list[ExtractedRelation]
    # Graph access for retrieval tools (replaces known_node_names)
    repo: MemoryRepository
    embeddings: EmbeddingService | None
    agent_id: str
    target_schema: str | None = None


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
            "You are a knowledge graph librarian with access to the existing graph. "
            "Your job is to integrate new extracted knowledge into the graph intelligently.",
            "Before creating or updating entities, use your tools to check what already exists.",
            "For each extracted entity:",
            "  1. Use find_node_by_name or search_existing_nodes to check if it exists",
            "  2. If it exists, inspect its current state and decide: update content? keep as-is?",
            "  3. If it's new, verify the type assignment against existing types",
            "For each extracted relation:",
            "  1. Use get_edges_between to check for existing relationships",
            "  2. If an edge exists with a different type, prefer the existing type unless "
            "the new type is clearly more accurate",
            "Normalize entity names to canonical forms.",
            "Preserve importance scores from extractor (max semantics if merging).",
        ),
    )

    # ── Read-only retrieval tools ──

    @agent.tool
    async def search_existing_nodes(
        ctx: RunContext[LibrarianAgentDeps],
        query: str,
        limit: int = 5,
    ) -> list[dict]:
        """Search the knowledge graph for nodes matching a query.
        Use this to check if an entity already exists before deciding
        to create a new node or update an existing one.

        Args:
            query: Search text (entity name, description fragment, etc.)
            limit: Max results to return (default 5)

        Returns:
            List of {name, type_name, content, importance, node_id} dicts
        """
        embedding = None
        if ctx.deps.embeddings:
            embedding = await ctx.deps.embeddings.embed(query)
        results = await ctx.deps.repo.search_nodes(
            ctx.deps.agent_id,
            query,
            limit=limit,
            query_embedding=embedding,
        )
        types = await ctx.deps.repo.get_node_types(ctx.deps.agent_id, target_schema=ctx.deps.target_schema)
        type_names = {t.id: t.name for t in types}
        out = []
        for node, score in results:
            out.append(
                {
                    "node_id": node.id,
                    "name": node.name,
                    "type_name": type_names.get(node.type_id, "Unknown"),
                    "content": node.content,
                    "importance": node.importance,
                    "relevance_score": round(score, 3),
                }
            )
        return out

    @agent.tool
    async def find_node_by_name(
        ctx: RunContext[LibrarianAgentDeps],
        name: str,
    ) -> list[dict]:
        """Look up a specific node by exact name (case-insensitive).
        Use this to check whether a specific entity already exists and
        what type and content it has.

        Args:
            name: Entity name to look up

        Returns:
            List of matching nodes (usually 0 or 1). Multiple means duplicates exist.
        """
        nodes = await ctx.deps.repo.find_nodes_by_name(
            ctx.deps.agent_id,
            name,
            target_schema=ctx.deps.target_schema,
        )
        types = await ctx.deps.repo.get_node_types(ctx.deps.agent_id, target_schema=ctx.deps.target_schema)
        type_map = {t.id: t.name for t in types}
        return [
            {
                "node_id": n.id,
                "name": n.name,
                "type_name": type_map.get(n.type_id, "Unknown"),
                "content": n.content,
                "importance": n.importance,
                "properties": n.properties,
            }
            for n in nodes
            if not n.forgotten
        ]

    @agent.tool
    async def inspect_node_neighborhood(
        ctx: RunContext[LibrarianAgentDeps],
        node_id: int,
        depth: int = 1,
    ) -> dict:
        """Inspect a node and its immediate neighborhood (connected nodes and edges).
        Use this after finding a node to understand its relationships before
        deciding how to update the graph.

        Args:
            node_id: The node ID (from search or find results)
            depth: How many hops to traverse (1 = immediate neighbors, 2 = 2-hop)

        Returns:
            Dict with center node info and list of connected edges and neighbors.
        """
        neighborhood = await ctx.deps.repo.get_node_neighborhood(
            agent_id=ctx.deps.agent_id,
            node_id=node_id,
            depth=min(depth, 2),
        )
        types = await ctx.deps.repo.get_node_types(ctx.deps.agent_id, target_schema=ctx.deps.target_schema)
        edge_types = await ctx.deps.repo.get_edge_types(ctx.deps.agent_id, target_schema=ctx.deps.target_schema)
        nt_map = {t.id: t.name for t in types}
        et_map = {t.id: t.name for t in edge_types}

        edges_out = []
        neighbors_out = []
        for entry in neighborhood:
            node = entry["node"]
            neighbors_out.append(
                {
                    "node_id": node.id,
                    "name": node.name,
                    "type": nt_map.get(node.type_id, "Unknown"),
                    "content": node.content[:100] if node.content else None,
                }
            )
            for edge in entry["edges"]:
                edges_out.append(
                    {
                        "edge_id": edge.id,
                        "source_id": edge.source_id,
                        "target_id": edge.target_id,
                        "type": et_map.get(edge.type_id, "Unknown"),
                        "weight": edge.weight,
                    }
                )
        return {"neighbors": neighbors_out, "edges": edges_out}

    @agent.tool
    async def get_edges_between(
        ctx: RunContext[LibrarianAgentDeps],
        source_name: str,
        target_name: str,
    ) -> list[dict]:
        """Find all edges between two named nodes.
        Use this before creating an edge to check if a relationship already exists.

        Args:
            source_name: Name of the source node
            target_name: Name of the target node

        Returns:
            List of existing edges between these nodes, with type and weight.
        """
        src_nodes = await ctx.deps.repo.find_nodes_by_name(
            ctx.deps.agent_id,
            source_name,
            target_schema=ctx.deps.target_schema,
        )
        tgt_nodes = await ctx.deps.repo.find_nodes_by_name(
            ctx.deps.agent_id,
            target_name,
            target_schema=ctx.deps.target_schema,
        )
        if not src_nodes or not tgt_nodes:
            return []

        edge_types = await ctx.deps.repo.get_edge_types(ctx.deps.agent_id, target_schema=ctx.deps.target_schema)
        et_map = {t.id: t.name for t in edge_types}

        # Get neighborhood and filter for edges to target
        src = src_nodes[0]
        tgt_ids = {n.id for n in tgt_nodes}
        neighborhood = await ctx.deps.repo.get_node_neighborhood(
            agent_id=ctx.deps.agent_id,
            node_id=src.id,
            depth=1,
        )
        result = []
        for entry in neighborhood:
            for edge in entry["edges"]:
                if edge.target_id in tgt_ids or edge.source_id in tgt_ids:
                    result.append(
                        {
                            "edge_id": edge.id,
                            "source_id": edge.source_id,
                            "target_id": edge.target_id,
                            "type": et_map.get(edge.type_id, "Unknown"),
                            "weight": edge.weight,
                            "properties": edge.properties,
                        }
                    )
        return result

    # ── Context injection ──

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
                "Extracted entities (from extractor — your job is to curate these):",
                entities_str,
                "",
                "Extracted relations:",
                relations_str,
                "",
                "IMPORTANT: Use your tools to check the existing graph before making decisions.",
                "Do NOT assume entities are new — always verify with find_node_by_name first.",
                "- ALWAYS provide a description for every entity, even if is_new=False.",
                "- For existing entities, write an UPDATED description that "
                "incorporates new information from the text.",
                "- The description becomes the entity's canonical summary — make it comprehensive and current.",
            ]
        )

    return agent  # ty: ignore[invalid-return-type]
