from __future__ import annotations

from typing import Protocol, runtime_checkable

from neocortex.domains.models import SemanticDomain


@runtime_checkable
class DomainService(Protocol):
    async def list_domains(self) -> list[SemanticDomain]: ...

    async def get_domain(self, slug: str) -> SemanticDomain | None: ...

    async def create_domain(
        self,
        slug: str,
        name: str,
        description: str,
        created_by: str,
        schema_name: str | None = None,
    ) -> SemanticDomain: ...

    async def update_schema_name(self, slug: str, schema_name: str) -> None: ...

    async def delete_domain(self, slug: str) -> bool: ...

    async def seed_defaults(self) -> None: ...
