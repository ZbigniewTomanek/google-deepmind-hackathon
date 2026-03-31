# Plan: Generic Model Provider Configuration

**Date**: 2026-03-31
**Branch**: `generic-model-provider` (from `functional-improvements`)
**Predecessors**: None
**Goal**: Replace hardcoded Google/Gemini model usage with Pydantic AI's string-based provider detection so users can switch providers via environment variables alone.

---

## Context

All Pydantic AI agent creation currently imports `GoogleModel` directly and passes
bare model names like `"gemini-3-flash-preview"`. This locks the system to Google
even though Pydantic AI natively supports provider-prefixed strings
(`"openai:gpt-4o"`, `"anthropic:claude-sonnet-4-5"`, `"google-gla:gemini-3-flash-preview"`)
that auto-detect the correct provider class with zero imports.

**Scope**: Only Pydantic AI agent models (extraction pipeline, domain classifier,
playground). Embedding service and media description service remain Google-only
(they use the raw `google-genai` SDK, not Pydantic AI).

**Affected model usage sites**:

| File | Current pattern |
|------|----------------|
| `src/neocortex/extraction/agents.py` | `GoogleModel(config.model_name)` |
| `src/neocortex/domains/classifier.py` | `GoogleModel(model_name)` |
| `src/pydantic_agents_playground/agents.py` | `GoogleModel(MODEL_NAME, provider=MODEL_PROVIDER)` |
| `src/neocortex/mcp_settings.py` | Defaults: `"gemini-3-flash-preview"` (bare, no provider prefix) |

---

## Strategy

Leverage Pydantic AI's built-in string-based model routing. No custom registry,
no provider enum, no mapping tables. The user sets `NEOCORTEX_ONTOLOGY_MODEL=openai:gpt-4o`
and it just works.

**Phase A (Stages 1-2)**: Foundation — update dependencies and settings format.
**Phase B (Stages 3-4)**: Agent code — remove GoogleModel imports, verify everything works.

---

## Success Criteria

| Metric | Baseline | Target | Rationale |
|--------|----------|--------|-----------|
| GoogleModel imports in agent code | 3 files | 0 files | No provider-specific imports |
| Provider extras in pyproject.toml | google only | google + openai + anthropic | Multi-provider support |
| Model string format in Pydantic AI settings | bare name | `provider:model` | Self-describing, provider-agnostic |
| Existing tests | pass | pass | No regressions |

---

## Files That May Be Changed

### Dependencies
- `pyproject.toml` -- add openai + anthropic extras to pydantic-ai-slim

### Configuration
- `src/neocortex/mcp_settings.py` -- change default model strings to provider-prefixed format

### Agent model instantiation
- `src/neocortex/extraction/agents.py` -- remove GoogleModel import, pass string directly
- `src/neocortex/domains/classifier.py` -- remove GoogleModel import, pass string directly
- `src/pydantic_agents_playground/agents.py` -- remove GoogleModel import, pass string directly

### Services
- ~~`src/neocortex/services.py`~~ -- no change needed; already passes `settings.domain_classifier_model` string through to `AgentDomainClassifier`

---

## Progress Tracker

| # | Stage | Status | Notes | Commit |
|---|-------|--------|-------|--------|
| 1 | [Dependencies](stages/01-dependencies.md) | PENDING | | |
| 2 | [Settings](stages/02-settings.md) | PENDING | | |
| 3 | [Agent code](stages/03-agent-code.md) | PENDING | | |
| 4 | [Verification](stages/04-verification.md) | PENDING | | |

Statuses: `PENDING` -> `IN_PROGRESS` -> `DONE` | `BLOCKED` | `SKIPPED`

---

## Execution Protocol

To execute this plan, follow this loop for each stage:

1. **Read the progress tracker** above and find the first stage that is not DONE
2. **Read the stage file** -- follow the link in the tracker to the stage's .md file
3. **Read resources** -- if the stage references shared resources,
   find them in the `resources/` directory
4. **Clarify ambiguities** -- if anything is unclear or multiple approaches exist,
   ask the user before implementing. Do not guess.
5. **Implement** -- execute the steps described in the stage
6. **Validate** -- run the verification checks listed in the stage.
   If validation fails, fix the issue before proceeding. Do not skip verification.
7. **Update this index** -- mark the stage as DONE in the progress tracker,
   add brief notes about what was done and any deviations
8. **Commit** -- create an atomic commit with the message specified in the stage.
   Include all changed files (code, config, docs, and this plan's index.md).

Repeat until all stages are DONE or a stage is BLOCKED.

**If a stage cannot be completed**: mark it BLOCKED in the tracker with a note
explaining why, and stop. Do not proceed to subsequent stages.

**If assumptions are wrong**: stop, document the issue in the Issues section below,
revise affected stages, and get user confirmation before continuing.

---

## Issues

[Document any problems discovered during execution]

---

## Decisions

1. **String passthrough over custom registry** -- Pydantic AI already handles
   `provider:model` string routing internally. Building our own registry would
   duplicate framework functionality and create the explicit hard-coded mappings
   the user wants to avoid.

2. **Embeddings and media stay Google-only** -- These use the raw `google-genai` SDK
   (not Pydantic AI) and have fundamentally different APIs per provider. Abstracting
   them is a separate concern and can be done later if needed.

3. **Provider extras in pyproject.toml** -- Include google + openai + anthropic as
   the three most common providers. Users needing groq/mistral/bedrock can add extras
   themselves. The `pydantic-ai-slim` approach keeps the install light.
