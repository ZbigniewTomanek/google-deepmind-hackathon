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


class TestSemanticDomainModel:
    def test_minimal_creation(self) -> None:
        domain = SemanticDomain(slug="test", name="Test", description="A test domain")
        assert domain.slug == "test"
        assert domain.id is None
        assert domain.schema_name is None
        assert domain.seed is False
