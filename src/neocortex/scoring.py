"""Hybrid recall scoring: combine vector similarity, text rank, recency, activation, and importance."""

from __future__ import annotations

import math
from datetime import UTC, datetime
from typing import NamedTuple


class HybridWeights(NamedTuple):
    vector: float
    text: float
    recency: float
    activation: float
    importance: float


def compute_recency_score(created_at: datetime, half_life_hours: float) -> float:
    """Exponential decay score based on age. Returns value in [0, 1]."""
    now = datetime.now(UTC)
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=UTC)
    hours_ago = max((now - created_at).total_seconds() / 3600.0, 0.0)
    return math.pow(2.0, -hours_ago / half_life_hours)


def compute_base_activation(
    access_count: int,
    last_accessed_at: datetime,
    decay_rate: float = 0.5,
) -> float:
    """ACT-R simplified base-level activation.

    B_i = ln(n + 1) - d * ln(T + 1)
    Normalized to [0, 1] via sigmoid.

    Args:
        access_count: Number of times the item has been recalled.
        last_accessed_at: When the item was last accessed.
        decay_rate: ACT-R ``d`` parameter (default 0.5).
    """
    now = datetime.now(UTC)
    if last_accessed_at.tzinfo is None:
        last_accessed_at = last_accessed_at.replace(tzinfo=UTC)
    hours_since = max((now - last_accessed_at).total_seconds() / 3600.0, 0.0)
    b_i = math.log(access_count + 1) - decay_rate * math.log(hours_since + 1)
    return 1.0 / (1.0 + math.exp(-b_i))


def compute_hybrid_score(
    vector_sim: float | None,
    text_rank: float | None,
    recency: float,
    activation: float | None,
    importance: float | None,
    weights: HybridWeights,
) -> float:
    """Compute a weighted hybrid score with graceful degradation.

    When a signal is ``None``, its weight is redistributed proportionally
    to the remaining signals. This means the system works identically to
    text-only when no embeddings exist, but improves as embeddings are added.
    """
    available: list[tuple[float, float]] = []  # (weight, value)
    if vector_sim is not None:
        available.append((weights.vector, vector_sim))
    if text_rank is not None:
        available.append((weights.text, text_rank))
    # Recency is always available.
    available.append((weights.recency, recency))
    if activation is not None:
        available.append((weights.activation, activation))
    if importance is not None:
        available.append((weights.importance, importance))

    total_weight = sum(w for w, _ in available)
    if total_weight <= 0:
        return 0.0

    return sum((w / total_weight) * v for w, v in available)


def compute_spreading_activation(
    seed_nodes: list[tuple[int, float]],
    neighborhood: dict[int, list[tuple[int, float]]],
    decay: float = 0.6,
    max_depth: int = 2,
) -> dict[int, float]:
    """Propagate activation energy from seed nodes through graph edges.

    Returns mapping of node_id -> accumulated activation bonus.
    Uses BFS with decaying energy propagation.
    """
    bonus: dict[int, float] = {}

    for seed_id, initial_score in seed_nodes:
        # BFS from this seed
        frontier: list[tuple[int, float]] = [(seed_id, initial_score)]
        visited: set[int] = {seed_id}

        for _depth in range(max_depth):
            next_frontier: list[tuple[int, float]] = []
            for node_id, energy in frontier:
                for neighbor_id, edge_weight in neighborhood.get(node_id, []):
                    if neighbor_id in visited:
                        continue
                    propagated = energy * edge_weight * decay
                    bonus[neighbor_id] = bonus.get(neighbor_id, 0.0) + propagated
                    visited.add(neighbor_id)
                    next_frontier.append((neighbor_id, propagated))
            frontier = next_frontier
            if not frontier:
                break

    # Normalize to [0, 1]
    if bonus:
        max_val = max(bonus.values())
        if max_val > 0:
            bonus = {k: v / max_val for k, v in bonus.items()}

    return bonus


def neighborhood_to_adjacency(
    neighborhood: list[dict],
    center_node_id: int,
) -> dict[int, list[tuple[int, float]]]:
    """Convert get_node_neighborhood() output to adjacency map for spreading activation.

    Builds a bidirectional adjacency map from the BFS neighborhood results.
    """
    adjacency: dict[int, list[tuple[int, float]]] = {}

    for entry in neighborhood:
        edges = entry.get("edges", [])
        for edge in edges:
            src = edge.source_id
            tgt = edge.target_id
            weight = edge.weight

            if src not in adjacency:
                adjacency[src] = []
            adjacency[src].append((tgt, weight))

            if tgt not in adjacency:
                adjacency[tgt] = []
            adjacency[tgt].append((src, weight))

    return adjacency
