"""Procrastinate-based async job queue for NeoCortex."""

from __future__ import annotations

import procrastinate


def create_job_app(conninfo: str) -> procrastinate.App:
    """Create a Procrastinate app connected to the NeoCortex database."""
    return procrastinate.App(
        connector=procrastinate.PsycopgConnector(conninfo=conninfo),
        import_paths=["neocortex.jobs.tasks"],
    )
