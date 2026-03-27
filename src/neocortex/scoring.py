"""Hybrid recall scoring: combine vector similarity, text rank, and recency."""

from __future__ import annotations

import math
from datetime import UTC, datetime
from typing import NamedTuple


class HybridWeights(NamedTuple):
    vector: float
    text: float
    recency: float


def compute_recency_score(created_at: datetime, half_life_hours: float) -> float:
    """Exponential decay score based on age. Returns value in [0, 1]."""
    now = datetime.now(UTC)
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=UTC)
    hours_ago = max((now - created_at).total_seconds() / 3600.0, 0.0)
    return math.pow(2.0, -hours_ago / half_life_hours)


def compute_hybrid_score(
    vector_sim: float | None,
    text_rank: float | None,
    recency: float,
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

    total_weight = sum(w for w, _ in available)
    if total_weight <= 0:
        return 0.0

    return sum((w / total_weight) * v for w, v in available)
