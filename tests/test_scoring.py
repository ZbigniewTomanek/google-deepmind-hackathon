"""Tests for neocortex.scoring — hybrid recall scoring functions."""

from datetime import UTC, datetime, timedelta

import pytest

from neocortex.mcp_settings import MCPSettings
from neocortex.scoring import (
    HybridWeights,
    compute_base_activation,
    compute_hybrid_score,
    compute_recency_score,
    mmr_rerank,
)

WEIGHTS = HybridWeights(vector=0.4, text=0.35, recency=0.25, activation=0.0, importance=0.0)


class TestRecencyScore:
    def test_recency_score_now(self):
        now = datetime.now(UTC)
        score = compute_recency_score(now, half_life_hours=168.0)
        assert score == pytest.approx(1.0, abs=0.01)

    def test_recency_score_one_half_life_ago(self):
        one_week_ago = datetime.now(UTC) - timedelta(hours=168)
        score = compute_recency_score(one_week_ago, half_life_hours=168.0)
        assert score == pytest.approx(0.5, abs=0.01)

    def test_recency_score_two_half_lives_ago(self):
        two_weeks_ago = datetime.now(UTC) - timedelta(hours=336)
        score = compute_recency_score(two_weeks_ago, half_life_hours=168.0)
        assert score == pytest.approx(0.25, abs=0.01)

    def test_recency_score_very_old(self):
        very_old = datetime.now(UTC) - timedelta(days=365)
        score = compute_recency_score(very_old, half_life_hours=168.0)
        assert score < 0.01

    def test_recency_score_naive_datetime_treated_as_utc(self):
        naive_now = datetime.now(UTC).replace(tzinfo=None)
        score = compute_recency_score(naive_now, half_life_hours=168.0)
        assert score == pytest.approx(1.0, abs=0.01)

    def test_recency_score_future_clamped(self):
        future = datetime.now(UTC) + timedelta(hours=10)
        score = compute_recency_score(future, half_life_hours=168.0)
        # hours_ago is clamped to 0, so score should be 1.0
        assert score == pytest.approx(1.0, abs=0.01)


class TestHybridScore:
    def test_hybrid_score_all_signals(self):
        score = compute_hybrid_score(
            vector_sim=0.9, text_rank=0.8, recency=0.7, activation=None, importance=None, weights=WEIGHTS
        )
        expected = 0.4 * 0.9 + 0.35 * 0.8 + 0.25 * 0.7
        assert score == pytest.approx(expected, abs=1e-9)

    def test_hybrid_score_no_vector(self):
        score = compute_hybrid_score(
            vector_sim=None, text_rank=0.8, recency=0.7, activation=None, importance=None, weights=WEIGHTS
        )
        # Redistributed: text gets 0.35/(0.35+0.25), recency gets 0.25/(0.35+0.25)
        total = 0.35 + 0.25
        expected = (0.35 / total) * 0.8 + (0.25 / total) * 0.7
        assert score == pytest.approx(expected, abs=1e-9)

    def test_hybrid_score_no_text(self):
        score = compute_hybrid_score(
            vector_sim=0.9, text_rank=None, recency=0.7, activation=None, importance=None, weights=WEIGHTS
        )
        total = 0.4 + 0.25
        expected = (0.4 / total) * 0.9 + (0.25 / total) * 0.7
        assert score == pytest.approx(expected, abs=1e-9)

    def test_hybrid_score_no_vector_no_text(self):
        score = compute_hybrid_score(
            vector_sim=None, text_rank=None, recency=0.7, activation=None, importance=None, weights=WEIGHTS
        )
        # Only recency — gets full weight
        assert score == pytest.approx(0.7, abs=1e-9)

    def test_hybrid_score_all_zero(self):
        score = compute_hybrid_score(
            vector_sim=0.0, text_rank=0.0, recency=0.0, activation=None, importance=None, weights=WEIGHTS
        )
        assert score == pytest.approx(0.0, abs=1e-9)

    def test_hybrid_score_perfect_scores(self):
        score = compute_hybrid_score(
            vector_sim=1.0, text_rank=1.0, recency=1.0, activation=None, importance=None, weights=WEIGHTS
        )
        assert score == pytest.approx(1.0, abs=1e-9)


class TestBaseActivation:
    """Tests for ACT-R base-level activation with sublinear dampening."""

    def test_activation_dampening_reduces_high_access(self):
        """access_count=50 with dampening should score lower than without."""
        now = datetime.now(UTC)
        undampened = compute_base_activation(50, now, decay_rate=0.5, access_exponent=1.0)
        dampened = compute_base_activation(50, now, decay_rate=0.5, access_exponent=0.5)
        assert dampened < undampened
        # Undampened is ~0.98; dampened is ~0.89 — significant reduction
        assert dampened < 0.90

    def test_activation_dampening_preserves_low_access(self):
        """access_count=1 should score similarly with and without dampening."""
        now = datetime.now(UTC)
        undampened = compute_base_activation(1, now, decay_rate=0.5, access_exponent=1.0)
        dampened = compute_base_activation(1, now, decay_rate=0.5, access_exponent=0.5)
        assert abs(undampened - dampened) < 0.05  # Minimal difference at low counts

    def test_activation_gravity_well_prevention(self):
        """After 20 accesses, dampened activation should be significantly below undampened."""
        now = datetime.now(UTC)
        dampened = compute_base_activation(20, now, decay_rate=0.5, access_exponent=0.5)
        undampened = compute_base_activation(20, now, decay_rate=0.5, access_exponent=1.0)
        # Dampened ~0.85 vs undampened ~0.95 — prevents gravity well
        assert dampened < 0.86
        assert undampened - dampened > 0.09

    def test_activation_zero_access(self):
        """Zero access count should produce a baseline activation around 0.5."""
        now = datetime.now(UTC)
        score = compute_base_activation(0, now, decay_rate=0.5, access_exponent=0.5)
        # ln(0^0.5 + 1) = ln(1) = 0, penalty ~0 for recent → sigmoid(0) = 0.5
        assert score == pytest.approx(0.5, abs=0.05)

    def test_activation_decays_with_time(self):
        """Older items should have lower activation than recent ones."""
        now = datetime.now(UTC)
        recent = compute_base_activation(5, now, decay_rate=0.5, access_exponent=0.5)
        old = compute_base_activation(5, now - timedelta(hours=168), decay_rate=0.5, access_exponent=0.5)
        assert old < recent

    def test_activation_exponent_one_matches_original(self):
        """With exponent=1.0, formula should match the original unbounded behavior."""
        now = datetime.now(UTC)
        score = compute_base_activation(10, now, decay_rate=0.5, access_exponent=1.0)
        # Original: sigmoid(ln(11) - 0.5*ln(1)) = sigmoid(ln(11)) = sigmoid(2.397)
        import math

        expected = 1.0 / (1.0 + math.exp(-math.log(11)))
        assert score == pytest.approx(expected, abs=0.01)


class TestMMRRerank:
    """Tests for Maximal Marginal Relevance diversity reranking."""

    def test_mmr_rerank_promotes_diversity(self):
        """Three similar items + one outlier: outlier should rank higher after MMR."""
        similar_emb = [1.0, 0.0, 0.0]
        outlier_emb = [0.0, 1.0, 0.0]
        results = [
            {"score": 0.9, "embedding": similar_emb, "name": "A"},
            {"score": 0.85, "embedding": similar_emb, "name": "B"},
            {"score": 0.80, "embedding": similar_emb, "name": "C"},
            {"score": 0.75, "embedding": outlier_emb, "name": "D"},
        ]
        reranked = mmr_rerank(results, lambda_param=0.7)
        names = [r["name"] for r in reranked]
        assert names[0] == "A"  # Highest score still first
        assert names.index("D") < names.index("C")  # Outlier promoted

    def test_mmr_lambda_1_preserves_order(self):
        """Lambda=1.0 should return original relevance order."""
        results = [
            {"score": 0.9, "embedding": [1, 0], "name": "A"},
            {"score": 0.5, "embedding": [0, 1], "name": "B"},
        ]
        reranked = mmr_rerank(results, lambda_param=1.0)
        assert [r["name"] for r in reranked] == ["A", "B"]

    def test_mmr_handles_missing_embeddings(self):
        """Items without embeddings appended at end."""
        results = [
            {"score": 0.9, "embedding": [1, 0], "name": "A"},
            {"score": 0.8, "embedding": None, "name": "B"},
            {"score": 0.7, "embedding": [0, 1], "name": "C"},
        ]
        reranked = mmr_rerank(results, lambda_param=0.7)
        assert reranked[-1]["name"] == "B"  # No embedding → last

    def test_mmr_single_result_passthrough(self):
        """Single result is returned as-is."""
        results = [{"score": 0.9, "embedding": [1, 0], "name": "A"}]
        assert mmr_rerank(results) == results

    def test_mmr_empty_results(self):
        """Empty list is returned as-is."""
        assert mmr_rerank([]) == []

    def test_mmr_all_missing_embeddings(self):
        """All items missing embeddings returns original list."""
        results = [
            {"score": 0.9, "embedding": None, "name": "A"},
            {"score": 0.5, "embedding": None, "name": "B"},
        ]
        reranked = mmr_rerank(results, lambda_param=0.7)
        assert reranked == results


class TestTemporalRecency:
    """Tests for temporal recency bias — using updated_at and weight rebalancing."""

    def test_recency_uses_updated_timestamp(self):
        """Node updated recently should score higher than stale node."""
        old_ts = datetime(2026, 1, 1, tzinfo=UTC)
        recent_ts = datetime(2026, 3, 30, tzinfo=UTC)
        old_score = compute_recency_score(old_ts, half_life_hours=168)
        updated_score = compute_recency_score(recent_ts, half_life_hours=168)
        assert updated_score > old_score * 2  # Significantly higher

    def test_default_weights_sum_to_one(self):
        """Default recall weights should sum to 1.0."""
        s = MCPSettings()
        total = (
            s.recall_weight_vector
            + s.recall_weight_text
            + s.recall_weight_recency
            + s.recall_weight_activation
            + s.recall_weight_importance
        )
        assert abs(total - 1.0) < 0.001
