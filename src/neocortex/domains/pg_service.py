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
    ) -> SemanticDomain:
        row = await self._pg.fetchrow(
            "INSERT INTO ontology_domains (slug, name, description, created_by, schema_name)"
            " VALUES ($1, $2, $3, $4, $5)"
            " RETURNING *",
            slug,
            name,
            description,
            created_by,
            schema_name,
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

    async def seed_defaults(self) -> None:
        from neocortex.domains.memory_service import _SEED_DOMAINS

        for d in _SEED_DOMAINS:
            await self._pg.execute(
                "INSERT INTO ontology_domains"
                " (slug, name, description, schema_name, seed)"
                " VALUES ($1, $2, $3, $4, true)"
                " ON CONFLICT (slug) DO NOTHING",
                d.slug,
                d.name,
                d.description,
                d.schema_name,
            )
