from __future__ import annotations

from datetime import UTC, datetime

from neocortex.domains.models import SEED_DOMAINS, SemanticDomain


class InMemoryDomainService:
    """In-memory domain service for testing and mock DB mode."""

    def __init__(self) -> None:
        self._domains: dict[str, SemanticDomain] = {}
        self._next_id = 1

    async def list_domains(self) -> list[SemanticDomain]:
        return sorted(self._domains.values(), key=lambda d: d.id or 0)

    async def get_domain(self, slug: str) -> SemanticDomain | None:
        return self._domains.get(slug)

    async def create_domain(
        self,
        slug: str,
        name: str,
        description: str,
        created_by: str,
        schema_name: str | None = None,
    ) -> SemanticDomain:
        if slug in self._domains:
            raise ValueError(f"Domain with slug '{slug}' already exists")
        domain = SemanticDomain(
            id=self._next_id,
            slug=slug,
            name=name,
            description=description,
            schema_name=schema_name,
            seed=False,
            created_at=datetime.now(UTC),
            created_by=created_by,
        )
        self._next_id += 1
        self._domains[slug] = domain
        return domain

    async def update_schema_name(self, slug: str, schema_name: str) -> None:
        domain = self._domains.get(slug)
        if domain is None:
            return
        self._domains[slug] = domain.model_copy(update={"schema_name": schema_name})

    async def delete_domain(self, slug: str) -> bool:
        domain = self._domains.get(slug)
        if domain is None:
            return False
        if domain.seed:
            return False
        del self._domains[slug]
        return True

    async def seed_defaults(self) -> None:
        for seed_domain in SEED_DOMAINS:
            if seed_domain.slug not in self._domains:
                domain = seed_domain.model_copy(
                    update={
                        "id": self._next_id,
                        "created_at": datetime.now(UTC),
                    }
                )
                self._next_id += 1
                self._domains[seed_domain.slug] = domain
