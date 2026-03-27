"""Tests for neocortex.scoring — hybrid recall scoring functions."""

from datetime import UTC, datetime, timedelta

import pytest

from neocortex.scoring import HybridWeights, compute_hybrid_score, compute_recency_score

WEIGHTS = HybridWeights(vector=0.4, text=0.35, recency=0.25)


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
        score = compute_hybrid_score(vector_sim=0.9, text_rank=0.8, recency=0.7, weights=WEIGHTS)
        expected = 0.4 * 0.9 + 0.35 * 0.8 + 0.25 * 0.7
        assert score == pytest.approx(expected, abs=1e-9)

    def test_hybrid_score_no_vector(self):
        score = compute_hybrid_score(vector_sim=None, text_rank=0.8, recency=0.7, weights=WEIGHTS)
        # Redistributed: text gets 0.35/(0.35+0.25), recency gets 0.25/(0.35+0.25)
        total = 0.35 + 0.25
        expected = (0.35 / total) * 0.8 + (0.25 / total) * 0.7
        assert score == pytest.approx(expected, abs=1e-9)

    def test_hybrid_score_no_text(self):
        score = compute_hybrid_score(vector_sim=0.9, text_rank=None, recency=0.7, weights=WEIGHTS)
        total = 0.4 + 0.25
        expected = (0.4 / total) * 0.9 + (0.25 / total) * 0.7
        assert score == pytest.approx(expected, abs=1e-9)

    def test_hybrid_score_no_vector_no_text(self):
        score = compute_hybrid_score(vector_sim=None, text_rank=None, recency=0.7, weights=WEIGHTS)
        # Only recency — gets full weight
        assert score == pytest.approx(0.7, abs=1e-9)

    def test_hybrid_score_all_zero(self):
        score = compute_hybrid_score(vector_sim=0.0, text_rank=0.0, recency=0.0, weights=WEIGHTS)
        assert score == pytest.approx(0.0, abs=1e-9)

    def test_hybrid_score_perfect_scores(self):
        score = compute_hybrid_score(vector_sim=1.0, text_rank=1.0, recency=1.0, weights=WEIGHTS)
        assert score == pytest.approx(1.0, abs=1e-9)
