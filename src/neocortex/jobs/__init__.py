"""Procrastinate-based async job queue for NeoCortex."""

from __future__ import annotations

import procrastinate


def create_job_app(conninfo: str) -> procrastinate.App:
    """Create a Procrastinate app connected to the NeoCortex database.

    Re-registers each task from the placeholder app onto a new App backed by a
    real PostgreSQL connector.  This avoids mutating the placeholder (which tests
    rely on) while ensuring ``app.configure_task(name).defer_async(...)`` uses
    the real database.
    """
    from neocortex.jobs import tasks as tasks_module

    connector = procrastinate.PsycopgConnector(conninfo=conninfo)
    real_app = procrastinate.App(connector=connector)

    # Re-register each user-defined task onto the real app
    for name, task in tasks_module.app.tasks.items():
        if name.startswith("builtin:") or "builtin_tasks" in name:
            continue
        real_app.tasks[name] = task.__class__(
            func=task.func,
            name=task.name,
            blueprint=real_app,
            queue=task.queue,
            lock=task.lock,
            queueing_lock=task.queueing_lock,
            retry=task.retry_strategy,  # ty: ignore[invalid-argument-type]
        )
    return real_app
