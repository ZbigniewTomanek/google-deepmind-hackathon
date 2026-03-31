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
    access_exponent: float = 0.5,
) -> float:
    """ACT-R simplified base-level activation with sublinear dampening.

    B_i = ln(n^a + 1) - d * ln(T + 1)  where a = access_exponent
    Normalized to [0, 1] via sigmoid.

    Args:
        access_count: Number of times the item has been recalled.
        last_accessed_at: When the item was last accessed.
        decay_rate: ACT-R ``d`` parameter (default 0.5).
        access_exponent: Sublinear dampening exponent (default 0.5 = sqrt).
            1.0 gives original unbounded growth; lower values compress high counts.
    """
    now = datetime.now(UTC)
    if last_accessed_at.tzinfo is None:
        last_accessed_at = last_accessed_at.replace(tzinfo=UTC)
    hours_since = max((now - last_accessed_at).total_seconds() / 3600.0, 0.0)
    dampened_count = math.pow(max(access_count, 0), access_exponent)
    frequency = math.log(dampened_count + 1)
    recency_penalty = decay_rate * math.log(hours_since + 1)
    b_i = frequency - recency_penalty
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


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Cosine similarity between two vectors. Returns value in [-1, 1]."""
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def mmr_rerank(
    results: list[dict],
    lambda_param: float = 0.7,
    score_key: str = "score",
    embedding_key: str = "embedding",
) -> list[dict]:
    """Maximal Marginal Relevance reranking for diversity.

    Iteratively selects items that balance high relevance with
    low similarity to already-selected items.

    Args:
        results: Scored recall results, each with a score and embedding.
        lambda_param: Trade-off between relevance (1.0) and diversity (0.0).
        score_key: Key for relevance score in result dicts.
        embedding_key: Key for embedding vector in result dicts.

    Returns:
        Reranked list in MMR order.
    """
    if len(results) <= 1 or lambda_param >= 1.0:
        return results

    # Filter to items that have embeddings (can't compute similarity without them)
    with_emb = [r for r in results if r.get(embedding_key) is not None]
    without_emb = [r for r in results if r.get(embedding_key) is None]

    if not with_emb:
        return results

    selected: list[dict] = []
    candidates = list(with_emb)

    # First pick: highest relevance score
    candidates.sort(key=lambda r: r[score_key], reverse=True)
    selected.append(candidates.pop(0))

    while candidates:
        best_mmr = -float("inf")
        best_idx = 0
        for i, cand in enumerate(candidates):
            relevance = cand[score_key]
            # Max cosine similarity to any already-selected item
            max_sim = max(_cosine_similarity(cand[embedding_key], s[embedding_key]) for s in selected)
            mmr_score = lambda_param * relevance - (1 - lambda_param) * max_sim
            if mmr_score > best_mmr:
                best_mmr = mmr_score
                best_idx = i
        selected.append(candidates.pop(best_idx))

    # Append items without embeddings at the end (no diversity signal available)
    return selected + without_emb


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
