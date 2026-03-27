"""Module-level holder for ServiceContext, set during lifespan."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from neocortex.services import ServiceContext

_services: ServiceContext | None = None


def set_services(ctx: ServiceContext) -> None:
    global _services
    _services = ctx


def get_services() -> ServiceContext:
    if _services is None:
        raise RuntimeError("Job services not initialized. Was set_services() called in lifespan?")
    return _services
