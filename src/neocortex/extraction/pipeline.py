"""Extraction pipeline orchestration.

Processes episodes through the 3-agent pipeline (ontology → extractor → librarian)
and persists the resulting knowledge graph via the MemoryRepository protocol.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from loguru import logger
from pydantic_ai.usage import UsageLimits

from neocortex.extraction.agents import (
    AgentInferenceConfig,
    ExtractorAgentDeps,
    LibrarianAgentDeps,
    OntologyAgentDeps,
    build_extractor_agent,
    build_librarian_agent,
    build_ontology_agent,
)
from neocortex.extraction.schemas import CurationSummary, LibrarianPayload

if TYPE_CHECKING:
    from neocortex.db.protocol import MemoryRepository
    from neocortex.embedding_service import EmbeddingService

_UNSET: str = "__UNSET__"


async def run_extraction(
    repo: MemoryRepository,
    embeddings: EmbeddingService | None,
    agent_id: str,
    episode_ids: list[int],
    target_schema: str | None = None,
    source_schema: str | None = _UNSET,
    ontology_config: AgentInferenceConfig | None = None,
    extractor_config: AgentInferenceConfig | None = None,
    librarian_config: AgentInferenceConfig | None = None,
    domain_hint: str | None = None,
    librarian_use_tools: bool = True,
    tool_calls_limit: int = 150,
) -> None:
    """Process episodes through the 3-agent pipeline and persist results.

    Args:
        repo: Storage backend (protocol implementation).
        embeddings: Embedding service for node vectors (may be None).
        agent_id: Agent whose graph is being populated.
        episode_ids: Episodes to process.
        target_schema: When set, writes target this schema instead of the agent's personal graph.
        source_schema: Schema to read episodes from. Default uses target_schema.
                       Pass None explicitly to read from the personal graph even when
                       target_schema is a shared schema (used by domain routing).
        ontology_config: Inference config for the ontology agent.
        extractor_config: Inference config for the extractor agent.
        librarian_config: Inference config for the librarian agent.
        domain_hint: Optional domain context (e.g. "Technical Knowledge: Programming languages, ...")
                     passed to ontology and extractor agents to guide type proposals.
        librarian_use_tools: When True (default), the librarian curates the graph
                             via tools. When False, falls back to _persist_payload.
    """
    ont_cfg = ontology_config or AgentInferenceConfig()
    ext_cfg = extractor_config or AgentInferenceConfig()
    lib_cfg = librarian_config or AgentInferenceConfig()

    read_schema: str | None = target_schema if source_schema is _UNSET else source_schema

    ontology_agent = build_ontology_agent(ont_cfg)
    extractor_agent = build_extractor_agent(ext_cfg)
    librarian_agent = build_librarian_agent(lib_cfg, use_tools=librarian_use_tools)

    for episode_id in episode_ids:
        episode = await repo.get_episode(agent_id, episode_id, target_schema=read_schema)
        if not episode:
            logger.warning("episode_not_found", episode_id=episode_id)
            continue

        text = episode.content
        logger.info(
            "extraction_start",
            episode_id=episode_id,
            agent_id=agent_id,
            target_schema=target_schema,
            text_len=len(text),
        )

        # 1. Load current ontology from the target graph
        node_types = await repo.get_node_types(agent_id, target_schema=target_schema)
        edge_types = await repo.get_edge_types(agent_id, target_schema=target_schema)

        # Build type description dicts for richer context
        node_type_descs = {t.name: (t.description or "") for t in node_types}
        edge_type_descs = {t.name: (t.description or "") for t in edge_types}

        # Fetch entity→type examples for context injection
        type_examples = await repo.get_type_examples(agent_id, target_schema=target_schema)

        # 2. Ontology stage
        ontology_result = await ontology_agent.run(
            f"Analyze this text and propose ontology extensions:\n\n{text}",
            deps=OntologyAgentDeps(
                episode_text=text,
                existing_node_types=[t.name for t in node_types],
                existing_edge_types=[t.name for t in edge_types],
                node_type_descriptions=node_type_descs,
                edge_type_descriptions=edge_type_descs,
                domain_hint=domain_hint,
                type_examples=type_examples,
            ),
            model_settings=ont_cfg.model_settings,
        )

        # 3. Persist new types (skip invalid names)
        for nt in ontology_result.output.new_node_types:
            if (
                await repo.get_or_create_node_type(agent_id, nt.name, nt.description, target_schema=target_schema)
                is None
            ):
                logger.warning("skipping_invalid_node_type", name=nt.name)
        for et in ontology_result.output.new_edge_types:
            if (
                await repo.get_or_create_edge_type(agent_id, et.name, et.description, target_schema=target_schema)
                is None
            ):
                logger.warning("skipping_invalid_edge_type", name=et.name)

        # Reload types (now includes newly created)
        node_types = await repo.get_node_types(agent_id, target_schema=target_schema)
        edge_types = await repo.get_edge_types(agent_id, target_schema=target_schema)
        node_type_descs = {t.name: (t.description or "") for t in node_types}
        edge_type_descs = {t.name: (t.description or "") for t in edge_types}

        # 4. Extraction stage
        extraction_result = await extractor_agent.run(
            f"Extract entities and relations from:\n\n{text}",
            deps=ExtractorAgentDeps(
                episode_text=text,
                node_types=[t.name for t in node_types],
                edge_types=[t.name for t in edge_types],
                node_type_descriptions=node_type_descs,
                edge_type_descriptions=edge_type_descs,
                domain_hint=domain_hint,
                type_examples=type_examples,
            ),
            model_settings=ext_cfg.model_settings,
        )

        # 5. Librarian stage
        if librarian_use_tools:
            # Tool-driven curation: librarian persists directly via tools
            # No cleanup_partial_curation needed: create_or_update_node uses upsert
            # semantics, so re-running the librarian is naturally idempotent.

            librarian_result = await librarian_agent.run(
                "Integrate the extracted entities and relations into the knowledge graph.",
                deps=LibrarianAgentDeps(
                    episode_text=text,
                    node_types=[t.name for t in node_types],
                    edge_types=[t.name for t in edge_types],
                    extracted_entities=extraction_result.output.entities,
                    extracted_relations=extraction_result.output.relations,
                    repo=repo,
                    embeddings=embeddings,
                    agent_id=agent_id,
                    target_schema=target_schema,
                    episode_id=episode_id,
                ),
                model_settings=lib_cfg.model_settings,
                usage_limits=UsageLimits(tool_calls_limit=tool_calls_limit),
            )

            # Mark episode as consolidated
            await repo.mark_episode_consolidated(agent_id, episode_id)

            # Log the curation summary
            summary = librarian_result.output
            assert isinstance(summary, CurationSummary)
            logger.bind(action_log=True).info(
                "curation_complete",
                episode_id=episode_id,
                agent_id=agent_id,
                created=summary.entities_created,
                updated=summary.entities_updated,
                archived=summary.entities_archived,
                edges_created=summary.edges_created,
                edges_removed=summary.edges_removed,
                summary=summary.summary,
            )

            # Clean up empty types created during this extraction
            await repo.cleanup_empty_types(agent_id, max_age_minutes=5, target_schema=target_schema)
        else:
            # Fallback: non-tool librarian → _persist_payload
            # Inject bounded name list for dedup context
            known_names = await repo.list_all_node_names(
                agent_id,
                target_schema=target_schema,
                limit=500,
            )

            librarian_result = await librarian_agent.run(
                "Normalize and deduplicate the extracted data.",
                deps=LibrarianAgentDeps(
                    episode_text=text,
                    node_types=[t.name for t in node_types],
                    edge_types=[t.name for t in edge_types],
                    extracted_entities=extraction_result.output.entities,
                    extracted_relations=extraction_result.output.relations,
                    repo=repo,
                    embeddings=embeddings,
                    agent_id=agent_id,
                    target_schema=target_schema,
                    episode_id=episode_id,
                    known_node_names=known_names,
                ),
                model_settings=lib_cfg.model_settings,
                usage_limits=UsageLimits(tool_calls_limit=tool_calls_limit),
            )

            # Build fallback map from extractor descriptions
            extractor_descriptions: dict[str, str] = {
                e.name: e.description for e in extraction_result.output.entities if e.description
            }

            payload = librarian_result.output
            assert isinstance(payload, LibrarianPayload)
            await _persist_payload(
                repo,
                embeddings,
                agent_id,
                episode_id,
                payload,
                target_schema=target_schema,
                extractor_descriptions=extractor_descriptions,
            )

            logger.info(
                "extraction_complete",
                episode_id=episode_id,
                agent_id=agent_id,
                target_schema=target_schema,
                entities=len(payload.entities),
                relations=len(payload.relations),
            )

            # Clean up empty types created during this extraction
            await repo.cleanup_empty_types(agent_id, max_age_minutes=5, target_schema=target_schema)


async def _persist_payload(
    repo: MemoryRepository,
    embeddings: EmbeddingService | None,
    agent_id: str,
    episode_id: int,
    payload: LibrarianPayload,
    target_schema: str | None = None,
    extractor_descriptions: dict[str, str] | None = None,
) -> None:
    """Persist librarian output to the knowledge graph.

    Kept as fallback for non-tool mode (librarian_use_tools=False).
    """

    # Fetch source episode to read importance_hint
    importance_hint: float | None = None
    episode = await repo.get_episode(agent_id, episode_id)
    if episode and episode.metadata:
        importance_hint = episode.metadata.get("importance_hint")

    # Persist any remaining type proposals (skip invalid names)
    for nt in payload.accepted_node_types:
        if await repo.get_or_create_node_type(agent_id, nt.name, nt.description, target_schema=target_schema) is None:
            logger.warning("skipping_invalid_node_type", name=nt.name)
    for et in payload.accepted_edge_types:
        if await repo.get_or_create_edge_type(agent_id, et.name, et.description, target_schema=target_schema) is None:
            logger.warning("skipping_invalid_edge_type", name=et.name)

    # Batch-embed entity descriptions (single API call instead of N+1)
    entity_embeddings: list[list[float] | None] = [None] * len(payload.entities)
    if embeddings:
        texts_to_embed = [e.description or "" for e in payload.entities]
        has_text = [bool(t) for t in texts_to_embed]
        if any(has_text):
            batch_results = await embeddings.embed_batch(
                [t for t, h in zip(texts_to_embed, has_text, strict=False) if h]
            )
            # Map batch results back to entity indices
            batch_idx = 0
            for i, h in enumerate(has_text):
                if h:
                    entity_embeddings[i] = batch_results[batch_idx]
                    batch_idx += 1
            assert batch_idx == len(
                batch_results
            ), f"Embedding batch size mismatch: expected {batch_idx}, got {len(batch_results)}"

    # Persist entities as nodes
    _extractor_desc = extractor_descriptions or {}
    name_to_node_id: dict[str, int] = {}
    for i, entity in enumerate(payload.entities):
        node_type = await repo.get_or_create_node_type(agent_id, entity.type_name, target_schema=target_schema)
        if node_type is None:
            logger.warning("skipping_entity_invalid_type", name=entity.name, type_name=entity.type_name)
            continue
        entity_importance = entity.importance
        if importance_hint is not None:
            entity_importance = max(entity_importance, importance_hint)
        # Fallback to extractor description when librarian returns None
        description = entity.description or _extractor_desc.get(entity.name)
        node = await repo.upsert_node(
            agent_id=agent_id,
            name=entity.name,
            type_id=node_type.id,
            content=description,
            properties={**entity.properties, "_source_episode": episode_id},
            embedding=entity_embeddings[i],
            target_schema=target_schema,
            importance=entity_importance,
        )
        name_to_node_id[entity.name] = node.id

    # Mark episode as consolidated (extraction completed)
    await repo.mark_episode_consolidated(agent_id, episode_id)

    # Persist relations as edges
    for rel in payload.relations:
        src_id = name_to_node_id.get(rel.source_name)
        tgt_id = name_to_node_id.get(rel.target_name)
        if src_id is None or tgt_id is None:
            # Try finding nodes by name in existing graph
            if src_id is None:
                src_nodes = await repo.find_nodes_by_name(agent_id, rel.source_name, target_schema=target_schema)
                src_id = src_nodes[0].id if src_nodes else None
            if tgt_id is None:
                tgt_nodes = await repo.find_nodes_by_name(agent_id, rel.target_name, target_schema=target_schema)
                tgt_id = tgt_nodes[0].id if tgt_nodes else None
        if src_id is None or tgt_id is None:
            logger.warning(
                "edge_skipped_missing_node",
                source=rel.source_name,
                target=rel.target_name,
            )
            continue
        edge_type = await repo.get_or_create_edge_type(agent_id, rel.relation_type, target_schema=target_schema)
        if edge_type is None:
            logger.warning("edge_skipped_invalid_type", relation_type=rel.relation_type)
            continue
        await repo.upsert_edge(
            agent_id=agent_id,
            source_id=src_id,
            target_id=tgt_id,
            type_id=edge_type.id,
            weight=rel.weight,
            properties={**rel.properties, "_source_episode": episode_id},
            target_schema=target_schema,
        )
