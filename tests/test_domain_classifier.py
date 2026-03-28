from __future__ import annotations

import pytest

from neocortex.domains import InMemoryDomainService
from neocortex.domains.classifier import DomainClassifier, MockDomainClassifier


class TestMockDomainClassifier:
    @pytest.fixture
    async def domains(self) -> list:
        svc = InMemoryDomainService()
        await svc.seed_defaults()
        return await svc.list_domains()

    @pytest.fixture
    def classifier(self) -> MockDomainClassifier:
        return MockDomainClassifier()

    @pytest.mark.asyncio
    async def test_prefer_python_matches_user_profile_and_technical(
        self, classifier: MockDomainClassifier, domains: list
    ) -> None:
        result = await classifier.classify("I prefer Python for backend work", domains)
        slugs = {m.domain_slug for m in result.matched_domains}
        assert "user_profile" in slugs
        assert "technical_knowledge" in slugs

    @pytest.mark.asyncio
    async def test_project_deadline_matches_work_context(self, classifier: MockDomainClassifier, domains: list) -> None:
        result = await classifier.classify("We need to ship project X by Friday", domains)
        slugs = {m.domain_slug for m in result.matched_domains}
        assert "work_context" in slugs

    @pytest.mark.asyncio
    async def test_react_hooks_matches_technical(self, classifier: MockDomainClassifier, domains: list) -> None:
        result = await classifier.classify("React hooks simplify state management", domains)
        slugs = {m.domain_slug for m in result.matched_domains}
        assert "technical_knowledge" in slugs

    @pytest.mark.asyncio
    async def test_theory_matches_domain_knowledge(self, classifier: MockDomainClassifier, domains: list) -> None:
        result = await classifier.classify("The theory of relativity explains gravitational effects", domains)
        slugs = {m.domain_slug for m in result.matched_domains}
        assert "domain_knowledge" in slugs

    @pytest.mark.asyncio
    async def test_fallback_to_domain_knowledge(self, classifier: MockDomainClassifier, domains: list) -> None:
        result = await classifier.classify("The weather is nice today", domains)
        assert len(result.matched_domains) == 1
        assert result.matched_domains[0].domain_slug == "domain_knowledge"
        assert result.matched_domains[0].confidence == 0.4

    @pytest.mark.asyncio
    async def test_all_confidences_above_threshold(self, classifier: MockDomainClassifier, domains: list) -> None:
        texts = [
            "I prefer Python for backend work",
            "We need to ship project X by Friday",
            "React hooks simplify state management",
            "The theory of relativity explains gravitational effects",
            "The weather is nice today",
        ]
        for text in texts:
            result = await classifier.classify(text, domains)
            for match in result.matched_domains:
                assert match.confidence >= 0.3, f"Confidence {match.confidence} below 0.3 for '{text}'"

    @pytest.mark.asyncio
    async def test_never_proposes_new_domains(self, classifier: MockDomainClassifier, domains: list) -> None:
        result = await classifier.classify("Something completely unrelated to anything", domains)
        assert result.proposed_domain is None

    @pytest.mark.asyncio
    async def test_implements_protocol(self, classifier: MockDomainClassifier) -> None:
        assert isinstance(classifier, DomainClassifier)
