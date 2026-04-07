from __future__ import annotations

import pytest

from neocortex.domains import InMemoryDomainService, SemanticDomain
from neocortex.domains.protocol import DomainService


class TestInMemoryDomainService:
    @pytest.fixture
    async def svc(self) -> InMemoryDomainService:
        svc = InMemoryDomainService()
        await svc.seed_defaults()
        return svc

    @pytest.mark.asyncio
    async def test_seed_defaults_creates_four_domains(self, svc: InMemoryDomainService) -> None:
        domains = await svc.list_domains()
        assert len(domains) == 4

    @pytest.mark.asyncio
    async def test_seed_defaults_sets_schema_names(self, svc: InMemoryDomainService) -> None:
        domains = await svc.list_domains()
        for domain in domains:
            assert domain.schema_name is not None
            assert domain.schema_name.startswith("ncx_shared__")

    @pytest.mark.asyncio
    async def test_get_domain_user_profile(self, svc: InMemoryDomainService) -> None:
        domain = await svc.get_domain("user_profile")
        assert domain is not None
        assert domain.slug == "user_profile"
        assert domain.name == "User Profile & Preferences"
        assert domain.schema_name == "ncx_shared__user_profile"
        assert domain.seed is True

    @pytest.mark.asyncio
    async def test_get_domain_returns_none_for_unknown(self, svc: InMemoryDomainService) -> None:
        domain = await svc.get_domain("nonexistent")
        assert domain is None

    @pytest.mark.asyncio
    async def test_create_domain_succeeds(self, svc: InMemoryDomainService) -> None:
        domain = await svc.create_domain(
            slug="custom_domain",
            name="Custom Domain",
            description="A custom test domain",
            created_by="test_agent",
            schema_name="ncx_shared__custom_domain",
        )
        assert domain.slug == "custom_domain"
        assert domain.id is not None
        assert domain.seed is False
        assert domain.created_by == "test_agent"

        # Verify it's in the list
        domains = await svc.list_domains()
        assert len(domains) == 5

    @pytest.mark.asyncio
    async def test_create_domain_duplicate_slug_raises(self, svc: InMemoryDomainService) -> None:
        with pytest.raises(ValueError, match="already exists"):
            await svc.create_domain(
                slug="user_profile",
                name="Duplicate",
                description="Should fail",
                created_by="test_agent",
            )

    @pytest.mark.asyncio
    async def test_update_schema_name_persists(self, svc: InMemoryDomainService) -> None:
        await svc.update_schema_name("user_profile", "ncx_shared__user_profile_v2")
        domain = await svc.get_domain("user_profile")
        assert domain is not None
        assert domain.schema_name == "ncx_shared__user_profile_v2"

    @pytest.mark.asyncio
    async def test_delete_seed_domain_returns_false(self, svc: InMemoryDomainService) -> None:
        result = await svc.delete_domain("user_profile")
        assert result is False
        # Domain still exists
        domain = await svc.get_domain("user_profile")
        assert domain is not None

    @pytest.mark.asyncio
    async def test_delete_non_seed_domain_returns_true(self, svc: InMemoryDomainService) -> None:
        await svc.create_domain(
            slug="custom",
            name="Custom",
            description="Temporary",
            created_by="test_agent",
        )
        result = await svc.delete_domain("custom")
        assert result is True
        domain = await svc.get_domain("custom")
        assert domain is None

    @pytest.mark.asyncio
    async def test_delete_nonexistent_returns_false(self, svc: InMemoryDomainService) -> None:
        result = await svc.delete_domain("nonexistent")
        assert result is False

    @pytest.mark.asyncio
    async def test_seed_defaults_idempotent(self, svc: InMemoryDomainService) -> None:
        await svc.seed_defaults()  # Called again (already called in fixture)
        domains = await svc.list_domains()
        assert len(domains) == 4

    @pytest.mark.asyncio
    async def test_implements_protocol(self, svc: InMemoryDomainService) -> None:
        assert isinstance(svc, DomainService)


class TestDomainHierarchy:
    @pytest.fixture
    async def svc(self) -> InMemoryDomainService:
        svc = InMemoryDomainService()
        await svc.seed_defaults()
        return svc

    @pytest.mark.asyncio
    async def test_seed_domains_are_roots(self, svc: InMemoryDomainService) -> None:
        domains = await svc.list_domains()
        for d in domains:
            assert d.parent_id is None
            assert d.depth == 0
            assert d.path == d.slug

    @pytest.mark.asyncio
    async def test_create_child_domain(self, svc: InMemoryDomainService) -> None:
        parent = await svc.get_domain("technical_knowledge")
        assert parent is not None
        child = await svc.create_domain(
            slug="python",
            name="Python",
            description="Python programming",
            created_by="test",
            parent_id=parent.id,
        )
        assert child.parent_id == parent.id
        assert child.depth == 1
        assert child.path == "technical_knowledge.python"

    @pytest.mark.asyncio
    async def test_create_grandchild_domain(self, svc: InMemoryDomainService) -> None:
        parent = await svc.get_domain("technical_knowledge")
        assert parent is not None
        child = await svc.create_domain(
            slug="python",
            name="Python",
            description="Python programming",
            created_by="test",
            parent_id=parent.id,
        )
        grandchild = await svc.create_domain(
            slug="django",
            name="Django",
            description="Django web framework",
            created_by="test",
            parent_id=child.id,
        )
        assert grandchild.depth == 2
        assert grandchild.path == "technical_knowledge.python.django"

    @pytest.mark.asyncio
    async def test_get_domain_tree(self, svc: InMemoryDomainService) -> None:
        parent = await svc.get_domain("technical_knowledge")
        assert parent is not None
        await svc.create_domain(
            slug="python",
            name="Python",
            description="Python programming",
            created_by="test",
            parent_id=parent.id,
        )
        tree = await svc.get_domain_tree()
        # All seed domains are roots
        assert len(tree) == 4
        # Find technical_knowledge and check it has children
        tk = next(d for d in tree if d.slug == "technical_knowledge")
        assert len(tk.children) == 1
        assert tk.children[0].slug == "python"

    @pytest.mark.asyncio
    async def test_get_children(self, svc: InMemoryDomainService) -> None:
        parent = await svc.get_domain("technical_knowledge")
        assert parent is not None
        await svc.create_domain(
            slug="python", name="Python", description="Python", created_by="test", parent_id=parent.id
        )
        await svc.create_domain(slug="rust", name="Rust", description="Rust", created_by="test", parent_id=parent.id)
        assert parent.id is not None
        children = await svc.get_children(parent.id)
        assert len(children) == 2
        slugs = {c.slug for c in children}
        assert slugs == {"python", "rust"}

    @pytest.mark.asyncio
    async def test_create_root_domain_without_parent(self, svc: InMemoryDomainService) -> None:
        domain = await svc.create_domain(
            slug="health",
            name="Health",
            description="Health domain",
            created_by="test",
        )
        assert domain.parent_id is None
        assert domain.depth == 0
        assert domain.path == "health"


class TestSemanticDomainModel:
    def test_minimal_creation(self) -> None:
        domain = SemanticDomain(slug="test", name="Test", description="A test domain")
        assert domain.slug == "test"
        assert domain.id is None
        assert domain.schema_name is None
        assert domain.seed is False

    def test_hierarchy_defaults(self) -> None:
        domain = SemanticDomain(slug="test", name="Test", description="A test domain")
        assert domain.parent_id is None
        assert domain.depth == 0
        assert domain.path == ""
        assert domain.children == []
