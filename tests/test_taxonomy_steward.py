"""Tests for the taxonomy steward report (Stage 6, Plan 30).

Unit-tests formatter and proposal heuristics with fixture DomainHealth data.
"""

from __future__ import annotations

from typing import Any

import pytest

from neocortex.domains.steward import (
    DomainHealth,
    StewardProposal,
    TaxonomySteward,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _seed_health(slug: str, name: str, **overrides: Any) -> DomainHealth:
    """Create a seed domain health fixture."""
    defaults: dict[str, Any] = dict(
        slug=slug,
        name=name,
        schema_name=f"ncx_shared__{slug}",
        depth=0,
        path=slug,
        seed=True,
        parent_slug=None,
    )
    defaults.update(overrides)
    return DomainHealth(**defaults)


def _child_health(slug: str, name: str, parent_slug: str, **overrides: Any) -> DomainHealth:
    """Create a non-seed child domain health fixture."""
    defaults: dict[str, Any] = dict(
        slug=slug,
        name=name,
        schema_name=f"ncx_shared__{slug}",
        depth=1,
        path=f"{parent_slug}.{slug}",
        seed=False,
        parent_slug=parent_slug,
    )
    defaults.update(overrides)
    return DomainHealth(**defaults)


@pytest.fixture
def sample_health() -> list[DomainHealth]:
    """A realistic set of domain health records for testing."""
    return [
        _seed_health(
            "user_profile",
            "User Profile",
            routed_episodes=8,
            active_nodes=20,
            edges=15,
            node_types_total=10,
            edge_types_total=8,
            node_types_used=5,
            edge_types_used=4,
            top_node_types=["Person", "Preference", "Goal", "Habit", "Location"],
            top_node_type_counts=[6, 5, 4, 3, 2],
        ),
        _seed_health(
            "technical_knowledge",
            "Technical Knowledge",
            routed_episodes=15,
            active_nodes=50,
            edges=40,
            node_types_total=12,
            edge_types_total=10,
            node_types_used=8,
            edge_types_used=6,
            top_node_types=["Language", "Framework", "Library", "Concept", "Pattern"],
            top_node_type_counts=[12, 10, 10, 9, 9],
        ),
        _seed_health(
            "work_context",
            "Work & Projects",
            routed_episodes=6,
            active_nodes=12,
            edges=8,
            node_types_total=8,
            edge_types_total=6,
            node_types_used=4,
            edge_types_used=3,
            top_node_types=["Project", "Task", "Person", "Meeting", "Decision"],
        ),
        _seed_health(
            "domain_knowledge",
            "Domain Knowledge",
            routed_episodes=3,
            active_nodes=5,
            edges=3,
            node_types_total=6,
            edge_types_total=4,
            node_types_used=3,
            edge_types_used=2,
            top_node_types=["Concept", "Fact", "Term"],
        ),
        _child_health(
            "rust_programming",
            "Rust Programming",
            parent_slug="technical_knowledge",
            routed_episodes=4,
            active_nodes=10,
            edges=8,
            node_types_total=6,
            edge_types_total=5,
            node_types_used=4,
            edge_types_used=3,
            top_node_types=["Crate", "Trait", "Module", "Concept"],
        ),
        _child_health(
            "marine_biology",
            "Marine Biology",
            parent_slug="domain_knowledge",
            routed_episodes=0,
            active_nodes=0,
            edges=0,
            node_types_total=0,
            edge_types_total=0,
            node_types_used=0,
            edge_types_used=0,
            top_node_types=[],
        ),
    ]


# We need a steward instance but only for proposal generation / formatting
# (no pool needed for those methods).


@pytest.fixture
def steward() -> TaxonomySteward:
    """A steward with a None pool — only used for non-DB methods."""
    return TaxonomySteward(pool=None)  # type: ignore[arg-type]  # ty: ignore[invalid-argument-type]


# ---------------------------------------------------------------------------
# Proposal heuristics
# ---------------------------------------------------------------------------


class TestSplitProposals:
    def test_split_proposed_for_high_volume_diverse_domain(self, steward: TaxonomySteward) -> None:
        """Domain with >=10 episodes and >=6 used types with low concentration gets split proposal."""
        health = [
            _seed_health(
                "technical_knowledge",
                "Technical Knowledge",
                routed_episodes=15,
                active_nodes=50,
                node_types_used=8,
                top_node_types=["A", "B", "C", "D", "E", "F", "G", "H"],
                top_node_type_counts=[8, 7, 7, 7, 6, 6, 5, 4],
            ),
        ]
        proposals = steward.generate_proposals(health)
        splits = [p for p in proposals if p.kind == "split"]
        assert len(splits) == 1
        assert "technical_knowledge" in splits[0].targets

    def test_no_split_for_low_volume(self, steward: TaxonomySteward) -> None:
        """Domain with few episodes should not get a split proposal."""
        health = [
            _seed_health(
                "domain_knowledge",
                "Domain Knowledge",
                routed_episodes=3,
                active_nodes=5,
                node_types_used=2,
            ),
        ]
        proposals = steward.generate_proposals(health)
        splits = [p for p in proposals if p.kind == "split"]
        assert len(splits) == 0

    def test_no_split_for_few_types(self, steward: TaxonomySteward) -> None:
        """High volume but few used types should not trigger split."""
        health = [
            _seed_health(
                "user_profile",
                "User Profile",
                routed_episodes=20,
                active_nodes=40,
                node_types_used=3,
            ),
        ]
        proposals = steward.generate_proposals(health)
        splits = [p for p in proposals if p.kind == "split"]
        assert len(splits) == 0


class TestMergeProposals:
    def test_merge_proposed_for_similar_siblings(self, steward: TaxonomySteward) -> None:
        """Siblings sharing >50% of top types get merge proposal."""
        health = [
            _child_health(
                "python_web",
                "Python Web Dev",
                parent_slug="technical_knowledge",
                top_node_types=["Framework", "Library", "API", "Route"],
            ),
            _child_health(
                "python_api",
                "Python APIs",
                parent_slug="technical_knowledge",
                top_node_types=["Framework", "Library", "API", "Endpoint"],
            ),
        ]
        proposals = steward.generate_proposals(health)
        merges = [p for p in proposals if p.kind == "merge"]
        assert len(merges) == 1
        assert set(merges[0].targets) == {"python_web", "python_api"}

    def test_no_merge_for_dissimilar_siblings(self, steward: TaxonomySteward) -> None:
        """Siblings with disjoint type sets should not get merge proposal."""
        health = [
            _child_health(
                "rust_prog",
                "Rust Programming",
                parent_slug="technical_knowledge",
                top_node_types=["Crate", "Trait", "Borrow", "Lifetime"],
            ),
            _child_health(
                "cooking_tips",
                "Cooking Tips",
                parent_slug="domain_knowledge",
                top_node_types=["Recipe", "Ingredient", "Technique", "Cuisine"],
            ),
        ]
        proposals = steward.generate_proposals(health)
        merges = [p for p in proposals if p.kind == "merge"]
        assert len(merges) == 0

    def test_no_merge_for_single_child(self, steward: TaxonomySteward) -> None:
        """A single child domain cannot merge with itself."""
        health = [
            _child_health(
                "only_child",
                "Only Child",
                parent_slug="domain_knowledge",
                top_node_types=["A", "B", "C"],
            ),
        ]
        proposals = steward.generate_proposals(health)
        merges = [p for p in proposals if p.kind == "merge"]
        assert len(merges) == 0


class TestDriftProposals:
    def test_drift_flagged_when_types_mismatch_slug(self, steward: TaxonomySteward) -> None:
        """Domain whose top types share no tokens with slug gets drift flag."""
        health = [
            _seed_health(
                "user_profile",
                "User Profile",
                active_nodes=10,
                top_node_types=["Recipe", "Ingredient", "Cuisine"],
            ),
        ]
        proposals = steward.generate_proposals(health)
        drifts = [p for p in proposals if p.kind == "description_drift"]
        assert len(drifts) == 1
        assert "user_profile" in drifts[0].targets

    def test_no_drift_when_types_match_slug(self, steward: TaxonomySteward) -> None:
        """Domain whose top types share tokens with slug should not be flagged."""
        health = [
            _seed_health(
                "technical_knowledge",
                "Technical Knowledge",
                active_nodes=20,
                top_node_types=["Technical_Standard", "Knowledge_Base", "API"],
            ),
        ]
        proposals = steward.generate_proposals(health)
        drifts = [p for p in proposals if p.kind == "description_drift"]
        assert len(drifts) == 0

    def test_no_drift_for_empty_domain(self, steward: TaxonomySteward) -> None:
        """Domain with no active nodes should not get drift flag."""
        health = [
            _seed_health(
                "user_profile",
                "User Profile",
                active_nodes=0,
                top_node_types=[],
            ),
        ]
        proposals = steward.generate_proposals(health)
        drifts = [p for p in proposals if p.kind == "description_drift"]
        assert len(drifts) == 0


class TestUnderutilizedProposals:
    def test_underutilized_flagged_for_low_traffic_non_seed(self, steward: TaxonomySteward) -> None:
        """Non-seed domain with <=1 routed episode gets underutilized flag."""
        health = [
            _seed_health(
                "technical_knowledge",
                "Technical Knowledge",
                routed_episodes=15,
            ),
            _child_health(
                "marine_biology",
                "Marine Biology",
                parent_slug="domain_knowledge",
                routed_episodes=0,
            ),
        ]
        proposals = steward.generate_proposals(health)
        under = [p for p in proposals if p.kind == "underutilized"]
        assert len(under) == 1
        assert "marine_biology" in under[0].targets

    def test_no_underutilized_for_seed_domains(self, steward: TaxonomySteward) -> None:
        """Seed domains should not be flagged as underutilized even with 0 episodes."""
        health = [
            _seed_health(
                "domain_knowledge",
                "Domain Knowledge",
                routed_episodes=0,
            ),
            _seed_health(
                "user_profile",
                "User Profile",
                routed_episodes=5,
            ),
        ]
        proposals = steward.generate_proposals(health)
        under = [p for p in proposals if p.kind == "underutilized"]
        assert len(under) == 0

    def test_no_underutilized_when_all_zero(self, steward: TaxonomySteward) -> None:
        """When the busiest domain has 0 episodes, no underutilized flags."""
        health = [
            _child_health(
                "a",
                "A",
                parent_slug="root",
                routed_episodes=0,
            ),
            _child_health(
                "b",
                "B",
                parent_slug="root",
                routed_episodes=0,
            ),
        ]
        proposals = steward.generate_proposals(health)
        under = [p for p in proposals if p.kind == "underutilized"]
        assert len(under) == 0


# ---------------------------------------------------------------------------
# Report formatting
# ---------------------------------------------------------------------------


class TestReportFormatting:
    def test_report_contains_all_sections(self, steward: TaxonomySteward, sample_health: list[DomainHealth]) -> None:
        """Report includes domain tree, metrics, proposals, and summary."""
        proposals = steward.generate_proposals(sample_health)
        report = steward.format_report(sample_health, proposals)

        assert "## Domain Tree" in report
        assert "## Domain Metrics" in report
        assert "## Proposals" in report
        assert "## Summary" in report

    def test_report_lists_all_domains(self, steward: TaxonomySteward, sample_health: list[DomainHealth]) -> None:
        """Every domain slug appears in the report."""
        report = steward.format_report(sample_health, [])
        for h in sample_health:
            assert h.slug in report

    def test_report_shows_seed_marker(self, steward: TaxonomySteward) -> None:
        """Seed domains are marked with (seed) in the tree."""
        health = [
            _seed_health("user_profile", "User Profile"),
            _child_health("child", "Child", parent_slug="user_profile"),
        ]
        report = steward.format_report(health, [])
        assert "(seed)" in report
        # Non-seed child should not have (seed)
        lines = report.split("\n")
        child_lines = [line for line in lines if "child" in line and "Domain Tree" not in line]
        assert child_lines
        assert all("(seed)" not in line for line in child_lines)

    def test_report_with_no_proposals(self, steward: TaxonomySteward) -> None:
        """Report with no proposals shows 'No proposals' message."""
        report = steward.format_report([], [])
        assert "No proposals at this time." in report

    def test_report_with_proposals(self, steward: TaxonomySteward) -> None:
        """Report includes proposal details."""
        health = [_seed_health("test", "Test")]
        proposals = [
            StewardProposal(
                kind="split",
                targets=["test"],
                reasoning="Test domain is too broad.",
            )
        ]
        report = steward.format_report(health, proposals)
        assert "**split**" in report
        assert "Test domain is too broad." in report

    def test_summary_counts(self, steward: TaxonomySteward, sample_health: list[DomainHealth]) -> None:
        """Summary includes correct counts."""
        report = steward.format_report(sample_health, [])
        assert "4 seed" in report
        assert "2 created" in report
        total_routed = sum(h.routed_episodes for h in sample_health)
        assert str(total_routed) in report


# ---------------------------------------------------------------------------
# DomainHealth defaults
# ---------------------------------------------------------------------------


class TestDomainHealthDefaults:
    def test_defaults_are_zero(self) -> None:
        """DomainHealth numeric fields default to 0."""
        h = DomainHealth(
            slug="test",
            name="Test",
            schema_name=None,
            depth=0,
            path="test",
            seed=False,
            parent_slug=None,
        )
        assert h.routed_episodes == 0
        assert h.active_nodes == 0
        assert h.edges == 0
        assert h.node_types_total == 0
        assert h.edge_types_total == 0
        assert h.node_types_used == 0
        assert h.edge_types_used == 0
        assert h.top_node_types == []
        assert h.top_node_type_counts == []


# ---------------------------------------------------------------------------
# generate_proposals integration
# ---------------------------------------------------------------------------


class TestGenerateProposalsIntegration:
    def test_full_sample_produces_expected_proposals(
        self, steward: TaxonomySteward, sample_health: list[DomainHealth]
    ) -> None:
        """Full sample data produces at least one split and one underutilized."""
        proposals = steward.generate_proposals(sample_health)
        kinds = {p.kind for p in proposals}
        # technical_knowledge has 15 episodes and 8 used types -> split
        assert "split" in kinds
        # marine_biology has 0 episodes and is non-seed -> underutilized
        assert "underutilized" in kinds
