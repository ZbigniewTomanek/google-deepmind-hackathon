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
        parent_id: int | None = None,
    ) -> SemanticDomain:
        if slug in self._domains:
            raise ValueError(f"Domain with slug '{slug}' already exists")

        # Compute depth and path from parent
        depth = 0
        path = slug
        if parent_id is not None:
            parent = next((d for d in self._domains.values() if d.id == parent_id), None)
            if parent is not None:
                depth = parent.depth + 1
                path = f"{parent.path}.{slug}"

        domain = SemanticDomain(
            id=self._next_id,
            slug=slug,
            name=name,
            description=description,
            schema_name=schema_name,
            seed=False,
            created_at=datetime.now(UTC),
            created_by=created_by,
            parent_id=parent_id,
            depth=depth,
            path=path,
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

    async def get_domain_tree(self) -> list[SemanticDomain]:
        # Copy domain objects to avoid mutating shared state in self._domains
        all_domains = sorted(
            [d.model_copy(update={"children": []}) for d in self._domains.values()],
            key=lambda d: (d.path, d.id or 0),
        )

        by_id: dict[int, SemanticDomain] = {}
        roots: list[SemanticDomain] = []
        for d in all_domains:
            if d.id is not None:
                by_id[d.id] = d
        for d in all_domains:
            if d.parent_id is not None and d.parent_id in by_id:
                by_id[d.parent_id].children.append(d)
            else:
                roots.append(d)
        return roots

    async def get_children(self, parent_id: int) -> list[SemanticDomain]:
        return sorted(
            [d for d in self._domains.values() if d.parent_id == parent_id],
            key=lambda d: d.id or 0,
        )

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
