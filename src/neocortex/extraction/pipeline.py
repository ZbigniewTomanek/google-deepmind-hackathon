"""Extraction pipeline orchestration.

Processes episodes through the 3-agent pipeline (ontology → extractor → librarian)
and persists the resulting knowledge graph via the MemoryRepository protocol.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from loguru import logger

from neocortex.extraction.agents import (
    ExtractorAgentDeps,
    LibrarianAgentDeps,
    OntologyAgentDeps,
    build_extractor_agent,
    build_librarian_agent,
    build_ontology_agent,
)
from neocortex.extraction.schemas import LibrarianPayload

if TYPE_CHECKING:
    from neocortex.db.protocol import MemoryRepository
    from neocortex.embedding_service import EmbeddingService


async def run_extraction(
    repo: MemoryRepository,
    embeddings: EmbeddingService | None,
    agent_id: str,
    episode_ids: list[int],
    model_name: str | None = None,
    use_test_model: bool = False,
) -> None:
    """Process episodes through the 3-agent pipeline and persist results.

    Args:
        repo: Storage backend (protocol implementation).
        embeddings: Embedding service for node vectors (may be None).
        agent_id: Agent whose graph is being populated.
        episode_ids: Episodes to process.
        model_name: LLM model name (from settings.extraction_model).
        use_test_model: If True, use pydantic_ai TestModel (for unit tests).
    """
    ontology_agent = build_ontology_agent(model_name, use_test_model)
    extractor_agent = build_extractor_agent(model_name, use_test_model)
    librarian_agent = build_librarian_agent(model_name, use_test_model)

    for episode_id in episode_ids:
        episode = await repo.get_episode(agent_id, episode_id)
        if not episode:
            logger.warning("episode_not_found", episode_id=episode_id)
            continue

        text = episode.content
        logger.info(
            "extraction_start",
            episode_id=episode_id,
            agent_id=agent_id,
            text_len=len(text),
        )

        # 1. Load current ontology from agent's graph
        node_types = await repo.get_node_types(agent_id)
        edge_types = await repo.get_edge_types(agent_id)

        # 2. Ontology stage
        ontology_result = await ontology_agent.run(
            f"Analyze this text and propose ontology extensions:\n\n{text}",
            deps=OntologyAgentDeps(
                episode_text=text,
                existing_node_types=[t.name for t in node_types],
                existing_edge_types=[t.name for t in edge_types],
            ),
        )

        # 3. Persist new types
        for nt in ontology_result.output.new_node_types:
            await repo.get_or_create_node_type(agent_id, nt.name, nt.description)
        for et in ontology_result.output.new_edge_types:
            await repo.get_or_create_edge_type(agent_id, et.name, et.description)

        # Reload types (now includes newly created)
        node_types = await repo.get_node_types(agent_id)
        edge_types = await repo.get_edge_types(agent_id)

        # 4. Extraction stage
        extraction_result = await extractor_agent.run(
            f"Extract entities and relations from:\n\n{text}",
            deps=ExtractorAgentDeps(
                episode_text=text,
                node_types=[t.name for t in node_types],
                edge_types=[t.name for t in edge_types],
            ),
        )

        # 5. Librarian stage
        known_names = await repo.list_all_node_names(agent_id)
        librarian_result = await librarian_agent.run(
            "Normalize and deduplicate the extracted data.",
            deps=LibrarianAgentDeps(
                episode_text=text,
                node_types=[t.name for t in node_types],
                edge_types=[t.name for t in edge_types],
                extracted_entities=extraction_result.output.entities,
                extracted_relations=extraction_result.output.relations,
                known_node_names=known_names,
            ),
        )

        # 6. Persist graph data
        payload = librarian_result.output
        await _persist_payload(repo, embeddings, agent_id, episode_id, payload)

        logger.info(
            "extraction_complete",
            episode_id=episode_id,
            agent_id=agent_id,
            entities=len(payload.entities),
            relations=len(payload.relations),
        )


async def _persist_payload(
    repo: MemoryRepository,
    embeddings: EmbeddingService | None,
    agent_id: str,
    episode_id: int,
    payload: LibrarianPayload,
) -> None:
    """Persist librarian output to the knowledge graph."""

    # Persist any remaining type proposals
    for nt in payload.accepted_node_types:
        await repo.get_or_create_node_type(agent_id, nt.name, nt.description)
    for et in payload.accepted_edge_types:
        await repo.get_or_create_edge_type(agent_id, et.name, et.description)

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
    name_to_node_id: dict[str, int] = {}
    for i, entity in enumerate(payload.entities):
        node_type = await repo.get_or_create_node_type(agent_id, entity.type_name)
        node = await repo.upsert_node(
            agent_id=agent_id,
            name=entity.name,
            type_id=node_type.id,
            content=entity.description,
            properties={**entity.properties, "_source_episode": episode_id},
            embedding=entity_embeddings[i],
        )
        name_to_node_id[entity.name] = node.id

    # Persist relations as edges
    for rel in payload.relations:
        src_id = name_to_node_id.get(rel.source_name)
        tgt_id = name_to_node_id.get(rel.target_name)
        if src_id is None or tgt_id is None:
            # Try finding nodes by name in existing graph
            if src_id is None:
                src_nodes = await repo.find_nodes_by_name(agent_id, rel.source_name)
                src_id = src_nodes[0].id if src_nodes else None
            if tgt_id is None:
                tgt_nodes = await repo.find_nodes_by_name(agent_id, rel.target_name)
                tgt_id = tgt_nodes[0].id if tgt_nodes else None
        if src_id is None or tgt_id is None:
            logger.warning(
                "edge_skipped_missing_node",
                source=rel.source_name,
                target=rel.target_name,
            )
            continue
        edge_type = await repo.get_or_create_edge_type(agent_id, rel.relation_type)
        await repo.upsert_edge(
            agent_id=agent_id,
            source_id=src_id,
            target_id=tgt_id,
            type_id=edge_type.id,
            weight=rel.weight,
            properties={**rel.properties, "_source_episode": episode_id},
        )
