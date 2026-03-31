"""Tests for edge weight management (Stage 5, Plan 16).

Covers diminishing-returns reinforcement, micro-decay, stale-edge decay,
weight floor enforcement, and convergence equilibrium.
All tests run against InMemoryRepository — no Docker needed.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from neocortex.db.mock import InMemoryRepository

AGENT = "test-agent"


@pytest.fixture
def repo() -> InMemoryRepository:
    return InMemoryRepository()


async def _create_edge(repo: InMemoryRepository, weight: float = 1.0) -> int:
    """Helper: create two nodes and one edge, return edge ID."""
    nt = await repo.get_or_create_node_type(AGENT, "Entity")
    et = await repo.get_or_create_edge_type(AGENT, "RELATES_TO")
    n1 = await repo.upsert_node(AGENT, "NodeA", nt.id)
    n2 = await repo.upsert_node(AGENT, "NodeB", nt.id)
    edge = await repo.upsert_edge(AGENT, n1.id, n2.id, et.id, weight=weight)
    assert edge is not None
    return edge.id


async def _create_multiple_edges(repo: InMemoryRepository, count: int, weight: float = 1.0) -> list[int]:
    """Helper: create ``count`` edges between distinct node pairs."""
    nt = await repo.get_or_create_node_type(AGENT, "Entity")
    et = await repo.get_or_create_edge_type(AGENT, "RELATES_TO")
    edge_ids = []
    for i in range(count):
        n1 = await repo.upsert_node(AGENT, f"Src{i}", nt.id)
        n2 = await repo.upsert_node(AGENT, f"Tgt{i}", nt.id)
        edge = await repo.upsert_edge(AGENT, n1.id, n2.id, et.id, weight=weight)
        assert edge is not None
        edge_ids.append(edge.id)
    return edge_ids


# ── 5.1 Diminishing-returns reinforcement ──


@pytest.mark.anyio
async def test_diminishing_returns_weight_under_1_5_after_20_reinforcements(repo: InMemoryRepository):
    """Reinforce same edge 20 times — weight must stay below 1.5."""
    eid = await _create_edge(repo, weight=1.0)

    for _ in range(20):
        await repo.reinforce_edges(AGENT, [eid], delta=0.05, ceiling=1.5)

    edge = repo._edges[eid]
    assert edge.weight < 1.5, f"Weight {edge.weight} should be < 1.5 after 20 reinforcements"


@pytest.mark.anyio
async def test_diminishing_returns_increments_decrease(repo: InMemoryRepository):
    """Each successive reinforcement should add less than the previous one."""
    eid = await _create_edge(repo, weight=1.0)
    increments = []

    for _ in range(10):
        before = repo._edges[eid].weight
        await repo.reinforce_edges(AGENT, [eid], delta=0.05, ceiling=1.5)
        after = repo._edges[eid].weight
        increments.append(after - before)

    # Each increment should be less than or equal to the previous
    for i in range(1, len(increments)):
        assert (
            increments[i] <= increments[i - 1] + 1e-9
        ), f"Increment {i} ({increments[i]:.6f}) should be <= increment {i-1} ({increments[i-1]:.6f})"


@pytest.mark.anyio
async def test_reinforcement_respects_ceiling(repo: InMemoryRepository):
    """Weight must never exceed the ceiling value."""
    eid = await _create_edge(repo, weight=1.4)

    for _ in range(50):
        await repo.reinforce_edges(AGENT, [eid], delta=0.05, ceiling=1.5)

    edge = repo._edges[eid]
    assert edge.weight <= 1.5, f"Weight {edge.weight} exceeds ceiling 1.5"


@pytest.mark.anyio
async def test_reinforcement_updates_last_reinforced_at(repo: InMemoryRepository):
    """Reinforcement should update last_reinforced_at timestamp."""
    eid = await _create_edge(repo, weight=1.0)
    before_ts = repo._edges[eid].last_reinforced_at

    await repo.reinforce_edges(AGENT, [eid], delta=0.05, ceiling=1.5)

    after_ts = repo._edges[eid].last_reinforced_at
    assert after_ts is not None
    if before_ts is not None:
        assert after_ts >= before_ts


# ── 5.3 Micro-decay ──


@pytest.mark.anyio
async def test_micro_decay_decays_non_excluded_edges(repo: InMemoryRepository):
    """Micro-decay should reduce weight of edges NOT in the exclude list."""
    edge_ids = await _create_multiple_edges(repo, 3, weight=1.2)

    # Reinforce all edges so they have recent last_reinforced_at
    for eid in edge_ids:
        await repo.reinforce_edges(AGENT, [eid], delta=0.01, ceiling=1.5)

    # Micro-decay excluding the first edge
    await repo.micro_decay_edges(
        AGENT,
        exclude_ids=[edge_ids[0]],
        factor=0.998,
        floor=0.1,
        recently_reinforced_hours=1.0,
    )

    # First edge should be unchanged (excluded)
    assert repo._edges[edge_ids[0]].weight > 1.2  # was reinforced, not decayed

    # Other edges should have decayed
    for eid in edge_ids[1:]:
        assert (
            repo._edges[eid].weight < 1.21 * 0.999
        ), f"Edge {eid} weight {repo._edges[eid].weight} should have decayed"


@pytest.mark.anyio
async def test_micro_decay_only_targets_recently_reinforced(repo: InMemoryRepository):
    """Micro-decay should only affect edges reinforced within the time window."""
    edge_ids = await _create_multiple_edges(repo, 2, weight=1.2)

    # Reinforce first edge recently
    await repo.reinforce_edges(AGENT, [edge_ids[0]], delta=0.01, ceiling=1.5)

    # Make second edge's reinforcement old (simulate by directly setting timestamp)
    old_edge = repo._edges[edge_ids[1]]
    repo._edges[edge_ids[1]] = old_edge.model_copy(
        update={"last_reinforced_at": datetime.now(UTC) - timedelta(hours=2)}
    )

    weight_before_0 = repo._edges[edge_ids[0]].weight
    weight_before_1 = repo._edges[edge_ids[1]].weight

    await repo.micro_decay_edges(
        AGENT,
        exclude_ids=[],
        factor=0.99,
        floor=0.1,
        recently_reinforced_hours=1.0,
    )

    # Recently reinforced edge should have decayed
    assert repo._edges[edge_ids[0]].weight < weight_before_0

    # Old edge should NOT have been touched (outside the window)
    assert repo._edges[edge_ids[1]].weight == weight_before_1


@pytest.mark.anyio
async def test_micro_decay_respects_floor(repo: InMemoryRepository):
    """Micro-decay must not push weight below the floor."""
    eid = (await _create_multiple_edges(repo, 1, weight=0.11))[0]

    # Reinforce so it has recent timestamp
    await repo.reinforce_edges(AGENT, [eid], delta=0.001, ceiling=1.5)

    # Apply aggressive decay
    for _ in range(100):
        await repo.micro_decay_edges(AGENT, exclude_ids=[], factor=0.9, floor=0.1, recently_reinforced_hours=1.0)

    assert repo._edges[eid].weight >= 0.1, f"Weight {repo._edges[eid].weight} went below floor 0.1"


# ── 5.4 Stale-edge decay ──


@pytest.mark.anyio
async def test_stale_decay_fires_for_48h_old_edges(repo: InMemoryRepository):
    """Edges not reinforced for 48+ hours should decay."""
    eid = await _create_edge(repo, weight=1.3)

    # Set last_reinforced_at to 3 days ago
    old_edge = repo._edges[eid]
    repo._edges[eid] = old_edge.model_copy(update={"last_reinforced_at": datetime.now(UTC) - timedelta(hours=72)})

    count = await repo.decay_stale_edges(AGENT, older_than_hours=48.0, decay_factor=0.95, floor=0.1)

    assert count == 1
    assert repo._edges[eid].weight == pytest.approx(1.3 * 0.95, rel=1e-6)


@pytest.mark.anyio
async def test_stale_decay_skips_recently_reinforced(repo: InMemoryRepository):
    """Edges reinforced within 48 hours should not be decayed."""
    eid = await _create_edge(repo, weight=1.3)

    # Reinforce recently
    await repo.reinforce_edges(AGENT, [eid], delta=0.01, ceiling=1.5)
    weight_after_reinforce = repo._edges[eid].weight

    count = await repo.decay_stale_edges(AGENT, older_than_hours=48.0, decay_factor=0.95, floor=0.1)

    assert count == 0
    assert repo._edges[eid].weight == weight_after_reinforce


@pytest.mark.anyio
async def test_stale_decay_respects_floor(repo: InMemoryRepository):
    """Stale decay must not push weight below the floor."""
    eid = await _create_edge(repo, weight=0.12)

    # Make it stale
    old_edge = repo._edges[eid]
    repo._edges[eid] = old_edge.model_copy(update={"last_reinforced_at": datetime.now(UTC) - timedelta(hours=72)})

    # Apply many rounds of decay
    for _ in range(50):
        await repo.decay_stale_edges(AGENT, older_than_hours=48.0, decay_factor=0.95, floor=0.1)

    assert repo._edges[eid].weight >= 0.1


# ── Equilibrium / convergence ──


@pytest.mark.anyio
async def test_weight_converges_under_repeated_reinforce_and_decay(repo: InMemoryRepository):
    """After many reinforce + decay cycles, weight should converge, not grow unbounded."""
    eid = await _create_edge(repo, weight=1.0)

    for _ in range(100):
        # Reinforce
        await repo.reinforce_edges(AGENT, [eid], delta=0.05, ceiling=1.5)
        # Micro-decay (simulating what happens on each recall — traversed edge excluded)
        await repo.micro_decay_edges(AGENT, exclude_ids=[eid], factor=0.998, floor=0.1, recently_reinforced_hours=1.0)

    weight = repo._edges[eid].weight
    # With exclude_ids=[eid], the traversed edge is never micro-decayed,
    # so it climbs to ceiling via diminishing returns. Verify ceiling respected.
    assert weight <= 1.5, f"Weight {weight} should be <= 1.5 (ceiling)"
    # And should be above the starting weight
    assert weight > 1.0, f"Weight {weight} should be > 1.0"
