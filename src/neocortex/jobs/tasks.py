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
) -> None:
    """Run extraction pipeline for a batch of episodes."""
    logger.info(
        "extract_episode_started",
        agent_id=agent_id,
        episode_ids=episode_ids,
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
    )
