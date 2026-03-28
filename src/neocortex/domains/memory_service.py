from __future__ import annotations

from datetime import UTC, datetime

from neocortex.domains.models import SemanticDomain

_SEED_DOMAINS = [
    SemanticDomain(
        slug="user_profile",
        name="User Profile & Preferences",
        description=(
            "Personal preferences, goals, habits, values, opinions, communication style, "
            "routines, and work style preferences. Knowledge about what the user likes, "
            "dislikes, wants to achieve, and how they prefer to work."
        ),
        schema_name="ncx_shared__user_profile",
        seed=True,
    ),
    SemanticDomain(
        slug="technical_knowledge",
        name="Technical Knowledge",
        description=(
            "Programming languages, frameworks, libraries, tools, architecture patterns, "
            "APIs, technical concepts, best practices, and engineering approaches. Knowledge "
            "about technologies, how they work, and how to use them."
        ),
        schema_name="ncx_shared__technical_knowledge",
        seed=True,
    ),
    SemanticDomain(
        slug="work_context",
        name="Work & Projects",
        description=(
            "Ongoing projects, tasks, deadlines, team members, organizations, meetings, "
            "decisions, and professional activities. Knowledge about what is being worked "
            "on, by whom, and when."
        ),
        schema_name="ncx_shared__work_context",
        seed=True,
    ),
    SemanticDomain(
        slug="domain_knowledge",
        name="Domain Knowledge",
        description=(
            "General factual knowledge, industry concepts, scientific facts, business "
            "concepts, market trends, and domain-specific expertise. Broad knowledge "
            "that does not fit the other specific categories."
        ),
        schema_name="ncx_shared__domain_knowledge",
        seed=True,
    ),
]


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
        for seed_domain in _SEED_DOMAINS:
            if seed_domain.slug not in self._domains:
                domain = seed_domain.model_copy(
                    update={
                        "id": self._next_id,
                        "created_at": datetime.now(UTC),
                    }
                )
                self._next_id += 1
                self._domains[seed_domain.slug] = domain
