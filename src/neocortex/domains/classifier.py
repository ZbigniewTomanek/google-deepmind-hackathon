"""Domain classification: PydanticAI agent and deterministic mock.

The DomainClassifier protocol classifies incoming knowledge text into one or
more semantic domains from the upper ontology.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from loguru import logger
from pydantic_ai import Agent
from pydantic_ai.settings import ModelSettings, ThinkingLevel

from neocortex.domains.models import (
    ClassificationResult,
    DomainClassification,
    SemanticDomain,
)


@runtime_checkable
class DomainClassifier(Protocol):
    async def classify(self, text: str, domains: list[SemanticDomain]) -> ClassificationResult: ...


class AgentDomainClassifier:
    """PydanticAI-based domain classifier."""

    def __init__(
        self,
        model_name: str = "google-gla:gemini-3-flash-preview",
        thinking_effort: ThinkingLevel = "low",
    ) -> None:
        self._model = model_name
        self._model_settings = ModelSettings(thinking=thinking_effort)

    async def classify(self, text: str, domains: list[SemanticDomain]) -> ClassificationResult:
        if not domains:
            logger.warning("classifier_received_empty_domains")
            return ClassificationResult(matched_domains=[], proposed_domain=None)

        domain_lines = "\n".join(f"- {d.slug}: {d.name}\n  {d.description}" for d in domains)
        prompt = (
            "You are a knowledge classification agent for a memory system.\n"
            "Classify incoming knowledge into one or more semantic domains.\n\n"
            "GUIDELINES:\n"
            "- CONSERVATIVE: strongly prefer existing domains over proposing new ones.\n"
            "- UNIFYING: knowledge should consolidate into fewer, broader domains, not scatter.\n"
            "- MULTI-LABEL: a single piece of knowledge may belong to multiple domains.\n"
            "- Only propose a new domain if the knowledge genuinely does not fit ANY existing domain.\n"
            "- New domains must be broad cross-cutting categories, NOT narrow topics or source-specific silos.\n"
            "- Set confidence >= 0.3 for relevant domains, higher for strong matches.\n\n"
            f"Available domains:\n{domain_lines}\n\n"
            "Classify the following knowledge text. Return matched domains with confidence scores."
        )

        agent: Agent[None, ClassificationResult] = Agent(  # ty: ignore[invalid-assignment]
            self._model,
            output_type=ClassificationResult,
            system_prompt=prompt,
        )

        result = await agent.run(text, model_settings=self._model_settings)
        logger.debug(
            "classification_result",
            matched_count=len(result.output.matched_domains),
            proposed=result.output.proposed_domain is not None,
        )

        # Fallback: if LLM returned no matches, try keyword matching
        if not result.output.matched_domains:
            return self._keyword_fallback(text, domains)

        return result.output

    def _keyword_fallback(self, text: str, domains: list[SemanticDomain]) -> ClassificationResult:
        """Keyword-based classification fallback when LLM returns no matches."""
        text_lower = text.lower()
        domain_slugs = {d.slug for d in domains}
        matches: list[DomainClassification] = []

        for slug, keywords in _KEYWORD_MAP.items():
            if slug not in domain_slugs:
                continue
            if any(kw in text_lower for kw in keywords):
                matches.append(
                    DomainClassification(
                        domain_slug=slug,
                        confidence=0.6,
                        reasoning="keyword_fallback",
                    )
                )

        # Default to domain_knowledge if nothing else matched
        if not matches and "domain_knowledge" in domain_slugs:
            matches.append(
                DomainClassification(
                    domain_slug="domain_knowledge",
                    confidence=0.4,
                    reasoning="default_fallback",
                )
            )

        return ClassificationResult(matched_domains=matches, proposed_domain=None)


# ── Keyword maps for the mock classifier ──

_KEYWORD_MAP: dict[str, list[str]] = {
    "user_profile": [
        "prefer",
        "goal",
        "habit",
        "like",
        "dislike",
        "want",
        "value",
        "opinion",
    ],
    "technical_knowledge": [
        "python",
        "react",
        "api",
        "database",
        "framework",
        "library",
        "code",
        "architecture",
    ],
    "work_context": [
        "project",
        "task",
        "deadline",
        "meeting",
        "team",
        "milestone",
        "sprint",
    ],
    "domain_knowledge": [
        "concept",
        "theory",
        "fact",
        "research",
        "trend",
        "industry",
    ],
}


class MockDomainClassifier:
    """Deterministic keyword-based classifier for tests."""

    async def classify(self, text: str, domains: list[SemanticDomain]) -> ClassificationResult:
        text_lower = text.lower()
        domain_slugs = {d.slug for d in domains}
        matched: list[DomainClassification] = []

        for slug, keywords in _KEYWORD_MAP.items():
            if slug not in domain_slugs:
                continue
            if any(kw in text_lower for kw in keywords):
                matched.append(
                    DomainClassification(
                        domain_slug=slug,
                        confidence=0.8,
                        reasoning=f"Keyword match for domain '{slug}'",
                    )
                )

        # Fallback to domain_knowledge if no keywords matched
        if not matched and "domain_knowledge" in domain_slugs:
            matched.append(
                DomainClassification(
                    domain_slug="domain_knowledge",
                    confidence=0.4,
                    reasoning="Fallback — no specific keyword matches",
                )
            )

        return ClassificationResult(matched_domains=matched)
