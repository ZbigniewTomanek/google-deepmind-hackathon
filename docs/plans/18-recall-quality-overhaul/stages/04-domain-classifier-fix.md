# Stage 4: Domain Classifier Fix

**Goal**: Fix domain routing so episodes are classified to shared domain graphs — the root cause is an empty domains list passed to the classifier.
**Dependencies**: None (independent of Phase A scoring fixes)

---

## Background

E2E testing showed ALL 28 episodes routed with `domain_count: 0`. Root cause analysis:

1. **Primary bug**: `DomainRouter.route_and_extract()` calls `self._domain_service.list_domains()` (router.py:59) which returns `[]` in the job execution context. The `AgentDomainClassifier.classify()` receives an empty `domains` list, generates a prompt with no available domains, and the LLM rationally returns zero matches.

2. **Why domains are empty**: The job task (`jobs/tasks.py`) creates its own service instances. If `seed_defaults()` hasn't been called in that context, or if the `PostgresDomainService` instance doesn't share the same connection pool state, the domains table may appear empty.

3. **No validation**: `DomainRouter` doesn't check for empty domains before calling the classifier. No warning logged.

4. **No fallback**: When the LLM classifier fails or returns nothing, there's no keyword-based fallback (even though `MockDomainClassifier` implements one).

**Fix approach**: Defense-in-depth with 3 layers:
- Fix the root cause (ensure domains are seeded in job context)
- Add validation (warn + return early on empty domains)
- Add keyword fallback in production classifier

---

## Steps

1. **Ensure domains are seeded in job context**
   - File: `src/neocortex/ingestion/episode_processor.py` (or wherever the job context initializes services)
   - Also check: `src/neocortex/jobs/tasks.py` (the route_episode task)
   - In the route_episode task setup, call `await domain_service.seed_defaults()` before invoking `route_and_extract()`. This is idempotent (uses `ON CONFLICT DO NOTHING`).
   - If the task gets a `domain_router` from a shared services dict, ensure that dict's initialization includes seeding.
   - Trace the actual service initialization path: `get_services()` in `tasks.py` → wherever the DomainRouter and its DomainService are created.

2. **Add empty-domains validation in `DomainRouter`**
   - File: `src/neocortex/domains/router.py`, method `route_and_extract` (around line 59)
   - After `domains = await self._domain_service.list_domains()`:
     ```python
     if not domains:
         logger.warning(
             "domain_routing_skipped",
             reason="no_domains_available",
             agent_id=agent_id,
             episode_id=episode_id,
         )
         return []
     ```

3. **Add empty-domains guard in `AgentDomainClassifier`**
   - File: `src/neocortex/domains/classifier.py`, method `classify` (around line 40)
   - Before building the prompt:
     ```python
     if not domains:
         logger.warning("classifier_received_empty_domains")
         return ClassificationResult(matched_domains=[], proposed_domains=[])
     ```

4. **Add keyword fallback to `AgentDomainClassifier`**
   - File: `src/neocortex/domains/classifier.py`
   - After the LLM classification call, if `matched_domains` is empty, fall back to keyword matching (reuse the logic from `MockDomainClassifier._KEYWORD_MAP`):
     ```python
     async def classify(self, text: str, domains: list[SemanticDomain]) -> ClassificationResult:
         # ... existing LLM classification ...
         result = await self._agent.run(prompt, ...)

         # Fallback: if LLM returned no matches, try keyword matching
         if not result.output.matched_domains:
             result = self._keyword_fallback(text, domains)

         return result

     def _keyword_fallback(self, text: str, domains: list[SemanticDomain]) -> ClassificationResult:
         """Keyword-based classification fallback when LLM returns no matches."""
         _KEYWORD_MAP = {
             "user_profile": ["prefer", "goal", "habit", "like", "dislike", "want", "value", "opinion", "style"],
             "technical_knowledge": ["python", "react", "api", "database", "framework", "library", "code", "architecture", "sql", "kubernetes", "docker", "git"],
             "work_context": ["project", "task", "deadline", "meeting", "team", "milestone", "sprint", "standup", "review", "deploy"],
             "domain_knowledge": ["concept", "theory", "fact", "research", "trend", "industry", "algorithm", "methodology"],
         }
         text_lower = text.lower()
         domain_slugs = {d.slug for d in domains}
         matches = []
         for slug, keywords in _KEYWORD_MAP.items():
             if slug not in domain_slugs:
                 continue
             if any(kw in text_lower for kw in keywords):
                 matches.append(DomainMatch(slug=slug, confidence=0.6, reason="keyword_fallback"))

         # Default to domain_knowledge if nothing else matched
         if not matches and "domain_knowledge" in domain_slugs:
             matches.append(DomainMatch(slug="domain_knowledge", confidence=0.4, reason="default_fallback"))

         return ClassificationResult(matched_domains=matches, proposed_domains=[])
     ```

5. **Add structured logging for classification results**
   - File: `src/neocortex/domains/router.py`
   - After classification, log the result for debugging:
     ```python
     logger.bind(action_log=True).info(
         "domain_classification_result",
         agent_id=agent_id,
         episode_id=episode_id,
         matched_count=len(classification.matched_domains),
         matched_slugs=[m.slug for m in classification.matched_domains],
         method="llm" if classification.matched_domains and classification.matched_domains[0].reason != "keyword_fallback" else "keyword_fallback",
     )
     ```

6. **Update domain tests**
   - File: `tests/test_domain_classifier.py`
   - Add tests:
     ```python
     async def test_classifier_empty_domains_returns_empty():
         """Classifier should return empty result when given no domains."""
         classifier = AgentDomainClassifier(...)
         result = await classifier.classify("some text about Python APIs", domains=[])
         assert len(result.matched_domains) == 0

     async def test_classifier_keyword_fallback():
         """When LLM returns no matches, keyword fallback should fire."""
         # Mock the LLM to return empty
         classifier = AgentDomainClassifier(...)
         # ... mock agent.run to return empty ClassificationResult ...
         result = await classifier.classify(
             "Working on the Python API database project",
             domains=SEED_DOMAINS,
         )
         assert len(result.matched_domains) > 0
         assert any(m.slug == "technical_knowledge" for m in result.matched_domains)
     ```
   - File: `tests/test_domain_router.py`
   - Add test:
     ```python
     async def test_router_handles_empty_domains():
         """Router should return empty list when domain service has no domains."""
         # Mock domain_service.list_domains() to return []
         results = await router.route_and_extract("agent1", 1, "some text")
         assert results == []
     ```

---

## Verification

- [ ] `uv run pytest tests/test_domain_classifier.py -v` — all tests pass
- [ ] `uv run pytest tests/test_domain_router.py -v` — all tests pass
- [ ] With a real or mock DB, store an episode with text "Working on the Python API project" and verify `domain_count > 0` in the log
- [ ] When `list_domains()` returns `[]`, router logs `domain_routing_skipped` and returns `[]` without error
- [ ] Keyword fallback triggers when LLM returns empty matches
- [ ] `NEOCORTEX_MOCK_DB=true uv run python -m neocortex` starts without errors

---

## Commit

`fix(domains): fix empty domain list bug, add keyword fallback for classification`
