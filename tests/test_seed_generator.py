"""Tests for dynamic seed generation (Stage 5, Plan 30)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from neocortex.domains.memory_service import InMemoryDomainService
from neocortex.domains.ontology_seeds import DOMAIN_SEEDS, DomainOntologySeed
from neocortex.domains.seed_generator import SeedGenerator


@pytest.fixture
async def domain_svc() -> InMemoryDomainService:
    svc = InMemoryDomainService()
    await svc.seed_defaults()
    return svc


@pytest.fixture
def generator(domain_svc: InMemoryDomainService) -> SeedGenerator:
    return SeedGenerator(domain_service=domain_svc, model="test-model")


# ── Static seed resolution ──


@pytest.mark.asyncio
async def test_static_seed_resolution(generator: SeedGenerator) -> None:
    """Static seeds in DOMAIN_SEEDS are returned directly without LLM call."""
    seed = await generator.resolve_seed("user_profile")
    assert seed is DOMAIN_SEEDS["user_profile"]
    assert len(seed.node_types) > 0
    assert len(seed.edge_types) > 0


@pytest.mark.asyncio
async def test_static_seed_for_all_builtin_domains(generator: SeedGenerator) -> None:
    """All four seed domains resolve from static seeds."""
    for slug in ("user_profile", "technical_knowledge", "work_context", "domain_knowledge"):
        seed = await generator.resolve_seed(slug)
        assert seed is DOMAIN_SEEDS[slug]


# ── Cache hit ──


@pytest.mark.asyncio
async def test_cache_hit(generator: SeedGenerator, domain_svc: InMemoryDomainService) -> None:
    """Second call for the same non-static slug returns cached seed."""
    await domain_svc.create_domain(
        slug="cooking",
        name="Cooking",
        description="Recipes and cooking techniques",
        created_by="test",
    )

    fake_seed = DomainOntologySeed(
        node_types={"Recipe": "A cooking recipe", "Ingredient": "Food ingredient"},
        edge_types={"HAS_INGREDIENT": "Recipe contains ingredient"},
    )

    with patch.object(generator, "_generate_seed", new_callable=AsyncMock, return_value=fake_seed) as mock_gen:
        first = await generator.resolve_seed("cooking")
        second = await generator.resolve_seed("cooking")

    assert first is second
    assert first is fake_seed
    # LLM generation should only be called once
    mock_gen.assert_called_once()


# ── Parent inheritance ──


@pytest.mark.asyncio
async def test_parent_inheritance(generator: SeedGenerator, domain_svc: InMemoryDomainService) -> None:
    """Child domain's seed generation receives parent seed as context."""
    # technical_knowledge is a seed domain with id
    parent = await domain_svc.get_domain("technical_knowledge")
    assert parent is not None

    await domain_svc.create_domain(
        slug="rust_programming",
        name="Rust Programming",
        description="Rust language knowledge",
        created_by="test",
        parent_id=parent.id,
    )

    fake_seed = DomainOntologySeed(
        node_types={"Crate": "Rust package", "Trait": "Rust trait"},
        edge_types={"IMPLEMENTS_TRAIT": "Type implements trait"},
    )

    with patch.object(generator, "_generate_seed", new_callable=AsyncMock, return_value=fake_seed) as mock_gen:
        seed = await generator.resolve_seed("rust_programming")

    assert seed is fake_seed
    # _generate_seed should receive the parent seed
    mock_gen.assert_called_once()
    call_kwargs = mock_gen.call_args
    assert call_kwargs[1]["parent_seed"] is DOMAIN_SEEDS["technical_knowledge"]


# ── LLM generation (mocked) ──


@pytest.mark.asyncio
async def test_llm_generation_called_for_novel_domain(
    generator: SeedGenerator, domain_svc: InMemoryDomainService
) -> None:
    """A novel domain without parent triggers LLM generation."""
    await domain_svc.create_domain(
        slug="marine_biology",
        name="Marine Biology",
        description="Study of ocean life",
        created_by="test",
    )

    fake_seed = DomainOntologySeed(
        node_types={
            "Species": "Marine organism",
            "Ecosystem": "Ocean ecosystem",
            "Habitat": "Living environment",
            "Organism": "Living creature",
            "Coral": "Coral structure",
            "Plankton": "Microscopic organism",
            "Current": "Ocean current",
            "Zone": "Ocean depth zone",
        },
        edge_types={
            "LIVES_IN": "Organism lives in habitat",
            "PART_OF": "Part of ecosystem",
            "FEEDS_ON": "Predation relationship",
            "SYMBIOTIC_WITH": "Symbiotic relationship",
            "FOUND_IN": "Found in zone",
            "PRODUCES": "Organism produces substance",
            "MIGRATES_TO": "Migration pattern",
            "ADAPTED_TO": "Environmental adaptation",
        },
    )

    with patch.object(generator, "_generate_seed", new_callable=AsyncMock, return_value=fake_seed):
        seed = await generator.resolve_seed("marine_biology")

    assert len(seed.node_types) >= 5
    assert len(seed.edge_types) >= 5


# ── Unknown domain (not in domain service) ──


@pytest.mark.asyncio
async def test_unknown_domain_still_generates(generator: SeedGenerator) -> None:
    """A slug not in the domain service still gets a generated seed."""
    fake_seed = DomainOntologySeed(
        node_types={"Thing": "Generic entity"},
        edge_types={"RELATES_TO": "Generic relation"},
    )

    with patch.object(generator, "_generate_seed", new_callable=AsyncMock, return_value=fake_seed):
        seed = await generator.resolve_seed("totally_unknown")

    assert seed.node_types == {"Thing": "Generic entity"}


# ── ServiceContext includes seed_generator ──


def test_service_context_has_seed_generator() -> None:
    """ServiceContext TypedDict includes seed_generator field."""
    from neocortex.services import ServiceContext

    annotations = ServiceContext.__annotations__
    assert "seed_generator" in annotations
