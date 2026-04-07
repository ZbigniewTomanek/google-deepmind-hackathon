from __future__ import annotations

from typing import Any

import asyncpg

from neocortex.domains.models import SemanticDomain
from neocortex.postgres_service import PostgresService


def _record_to_domain(row: asyncpg.Record) -> SemanticDomain:
    """Convert an asyncpg Record to a SemanticDomain."""
    data: dict[str, Any] = dict(row.items())
    # Drop updated_at since SemanticDomain doesn't have it
    data.pop("updated_at", None)
    return SemanticDomain.model_validate(data)


class PostgresDomainService:
    """PostgreSQL-backed domain service using the ontology_domains table."""

    def __init__(self, pg: PostgresService) -> None:
        self._pg = pg

    async def list_domains(self) -> list[SemanticDomain]:
        rows = await self._pg.fetch("SELECT * FROM ontology_domains ORDER BY id")
        return [_record_to_domain(row) for row in rows]

    async def get_domain(self, slug: str) -> SemanticDomain | None:
        row = await self._pg.fetchrow("SELECT * FROM ontology_domains WHERE slug = $1", slug)
        if row is None:
            return None
        return _record_to_domain(row)

    async def create_domain(
        self,
        slug: str,
        name: str,
        description: str,
        created_by: str,
        schema_name: str | None = None,
        parent_id: int | None = None,
    ) -> SemanticDomain:
        # Compute depth and path from parent
        depth = 0
        path = slug
        if parent_id is not None:
            parent_row = await self._pg.fetchrow("SELECT depth, path FROM ontology_domains WHERE id = $1", parent_id)
            if parent_row is not None:
                depth = parent_row["depth"] + 1
                path = f"{parent_row['path']}.{slug}"

        row = await self._pg.fetchrow(
            "INSERT INTO ontology_domains (slug, name, description, created_by, schema_name, parent_id, depth, path)"
            " VALUES ($1, $2, $3, $4, $5, $6, $7, $8)"
            " RETURNING *",
            slug,
            name,
            description,
            created_by,
            schema_name,
            parent_id,
            depth,
            path,
        )
        assert row is not None  # RETURNING always produces a row
        return _record_to_domain(row)

    async def update_schema_name(self, slug: str, schema_name: str) -> None:
        await self._pg.execute(
            "UPDATE ontology_domains SET schema_name = $1, updated_at = now() WHERE slug = $2",
            schema_name,
            slug,
        )

    async def delete_domain(self, slug: str) -> bool:
        result = await self._pg.execute(
            "DELETE FROM ontology_domains WHERE slug = $1 AND seed = false",
            slug,
        )
        return result != "DELETE 0"

    async def get_domain_tree(self) -> list[SemanticDomain]:
        rows = await self._pg.fetch("SELECT * FROM ontology_domains ORDER BY path, id")
        all_domains = [_record_to_domain(row) for row in rows]

        # Build tree: index by id, then attach children
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
        rows = await self._pg.fetch(
            "SELECT * FROM ontology_domains WHERE parent_id = $1 ORDER BY id",
            parent_id,
        )
        return [_record_to_domain(row) for row in rows]

    async def seed_defaults(self) -> None:
        from neocortex.domains.models import SEED_DOMAINS

        for d in SEED_DOMAINS:
            await self._pg.execute(
                "INSERT INTO ontology_domains"
                " (slug, name, description, schema_name, seed, parent_id, depth, path)"
                " VALUES ($1, $2, $3, $4, true, $5, $6, $7)"
                " ON CONFLICT (slug) DO NOTHING",
                d.slug,
                d.name,
                d.description,
                d.schema_name,
                d.parent_id,
                d.depth,
                d.path,
            )
