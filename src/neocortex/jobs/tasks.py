"""Procrastinate task definitions for NeoCortex."""

from __future__ import annotations

import procrastinate
from loguru import logger
from procrastinate.testing import InMemoryConnector

# Placeholder app for task registration — replaced at runtime with real conninfo.
app = procrastinate.App(
    connector=InMemoryConnector(),
    import_paths=["neocortex.jobs.tasks"],
)


@app.task(
    name="extract_episode",
    retry=procrastinate.RetryStrategy(max_attempts=3, wait=5),
    queue="extraction",
)
async def extract_episode(
    agent_id: str,
    episode_ids: list[int],
    target_schema: str | None = None,
    source_schema: str | None = None,
) -> None:
    """Run extraction pipeline for a batch of episodes.

    Args:
        agent_id: Agent whose graph is being populated.
        episode_ids: Episodes to process.
        target_schema: Schema to write extracted nodes/edges to.
        source_schema: Schema to read episodes from (defaults to target_schema).
                       Used by domain routing where episodes live in the personal
                       graph but results go to a shared domain schema.
    """
    logger.info(
        "extract_episode_started",
        agent_id=agent_id,
        episode_ids=episode_ids,
        target_schema=target_schema,
        source_schema=source_schema,
    )
    from neocortex.extraction.agents import AgentInferenceConfig
    from neocortex.extraction.pipeline import run_extraction
    from neocortex.jobs.context import get_services

    services = get_services()
    settings = services["settings"]

    await run_extraction(
        repo=services["repo"],
        embeddings=services["embeddings"],
        agent_id=agent_id,
        episode_ids=episode_ids,
        target_schema=target_schema,
        source_schema=source_schema,
        ontology_config=AgentInferenceConfig(
            model_name=settings.ontology_model,
            thinking_effort=settings.ontology_thinking_effort,
        ),
        extractor_config=AgentInferenceConfig(
            model_name=settings.extractor_model,
            thinking_effort=settings.extractor_thinking_effort,
        ),
        librarian_config=AgentInferenceConfig(
            model_name=settings.librarian_model,
            thinking_effort=settings.librarian_thinking_effort,
        ),
    )
    logger.info(
        "extract_episode_completed",
        agent_id=agent_id,
        episode_ids=episode_ids,
        target_schema=target_schema,
    )


@app.task(
    name="route_episode",
    retry=procrastinate.RetryStrategy(max_attempts=3, wait=5),
    queue="extraction",
)
async def route_episode(
    agent_id: str,
    episode_id: int,
    episode_text: str,
) -> None:
    """Route an episode to shared graphs via domain classification."""
    logger.info("route_episode_started", agent_id=agent_id, episode_id=episode_id)
    from neocortex.jobs.context import get_services

    services = get_services()
    domain_router = services.get("domain_router")
    if domain_router is None:
        logger.debug("route_episode_skipped_no_router")
        return

    results = await domain_router.route_and_extract(
        agent_id=agent_id,
        episode_id=episode_id,
        episode_text=episode_text,
    )
    logger.bind(action_log=True).info(
        "route_episode_completed",
        agent_id=agent_id,
        episode_id=episode_id,
        routed_to=[r.schema_name for r in results],
        domain_count=len(results),
    )
