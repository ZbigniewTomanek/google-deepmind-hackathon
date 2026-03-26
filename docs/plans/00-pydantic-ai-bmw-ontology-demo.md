# Plan: Pydantic AI BMW Ontology Demo

## Overview
Build a lightweight demo under `src/pydantic_agents_playground` that processes a fixed set of 10 BMW 3 Series messages one at a time through a three-agent Pydantic AI pipeline backed by Google Gemini Flash Preview. The pipeline will (1) propose and extend a lightweight OWL-like ontology, (2) extract ontology-aligned facts from each message, and (3) persist the evolving ontology and facts into SQLite through a librarian stage. The implementation should be runnable as a small CLI and should include a dry-run path for local verification when a live Google API key is unavailable.

## Execution Protocol

To execute this plan, follow this loop for each stage:

1. Read the progress tracker below and find the first stage that is not DONE
2. Read the stage details and confirm dependencies are satisfied
3. Clarify ambiguities before editing if a stage requires a materially different approach
4. Implement only the scope described in the current stage
5. Validate using the verification checks listed in the stage
6. Update this plan by marking the stage status and notes
7. Commit atomically with the message listed for the stage if commits are requested

If a stage cannot be completed, mark it `BLOCKED`, document the reason in `Issues`, and stop.

If assumptions change materially during implementation, revise this plan before continuing.

## Progress Tracker

| # | Stage | Status | Notes | Commit |
|---|-------|--------|-------|--------|
| 1 | Project scaffold and dependency setup | PENDING | | `feat(pydantic-playground): scaffold BMW ontology demo` |
| 2 | Multi-agent ontology, extraction, and SQLite pipeline | PENDING | | `feat(pydantic-playground): add ontology extraction pipeline` |
| 3 | CLI, documentation, and verification | PENDING | | `docs(pydantic-playground): document demo usage` |

Statuses: `PENDING` -> `IN_PROGRESS` -> `DONE` | `BLOCKED`

---

## Stage 1: Project scaffold and dependency setup
**Goal**: Create the package skeleton and add the minimum dependencies needed for Pydantic AI with Google Gemini.
**Dependencies**: None

**Steps**:
1. Add runtime dependencies to `pyproject.toml` for `pydantic-ai-slim[google]` and any other minimal packages needed by the demo.
2. Create `src/pydantic_agents_playground/` with initial package files and module layout for messages, schemas, database access, agent wiring, and CLI entrypoint.
3. Decide the demo architecture in code comments and module naming so the package clearly reflects the three-stage flow: ontology agent -> extractor agent -> librarian agent.

**Verification**:
- [ ] The new package imports without syntax errors
- [ ] Dependency declarations are present in `pyproject.toml`

**Commit**: `feat(pydantic-playground): scaffold BMW ontology demo`

---

## Stage 2: Multi-agent ontology, extraction, and SQLite pipeline
**Goal**: Implement the end-to-end Pydantic AI workflow that updates ontology and facts after each message.
**Dependencies**: Stage 1

**Steps**:
1. Define structured Pydantic output models for ontology proposals, extracted entities/facts, and librarian persistence decisions.
2. Implement the fixed corpus of 10 BMW 3 Series messages covering different aspects such as motorsport, engines, trim lines, and model generations.
3. Implement SQLite persistence for ontology classes, ontology properties, source messages, extracted entities, and fact assertions.
4. Implement the ontology agent using Gemini Flash Preview with instructions that extend the ontology conservatively and generically from the current ontology plus the next message.
5. Implement the extractor agent so it maps message content into ontology-aligned entities and fact assertions.
6. Implement the librarian agent so it normalizes extracted content against the ontology and returns the final persistence payload applied by application code.
7. Implement the orchestration loop that processes messages sequentially, refreshes ontology state after each message, and stores per-message run results.

**Verification**:
- [ ] The pipeline can run end-to-end in a dry-run or test-model mode without network credentials
- [ ] The live model configuration defaults to `google-gla:gemini-3-flash-preview`
- [ ] SQLite output contains ontology and fact rows after processing the sample corpus

**Commit**: `feat(pydantic-playground): add ontology extraction pipeline`

---

## Stage 3: CLI, documentation, and verification
**Goal**: Make the demo runnable and easy to evaluate for fit.
**Dependencies**: Stage 2

**Steps**:
1. Add a CLI entrypoint for running the demo with options for database path, reset behavior, and optional dry-run or test-model execution.
2. Update `README.md` or add focused documentation explaining environment variables, how the three agents interact, and how to inspect the SQLite results.
3. Run local verification commands that are realistic for this repo and capture any known limits, especially around live Gemini execution requiring `GOOGLE_API_KEY`.

**Verification**:
- [ ] The CLI help or invocation path is documented
- [ ] A local verification command succeeds in this environment
- [ ] Documentation explains both live and offline verification paths

**Commit**: `docs(pydantic-playground): document demo usage`

---

## Overall Verification

1. Run the demo in offline verification mode and confirm it creates the SQLite database and stores ontology plus fact rows.
2. If `GOOGLE_API_KEY` is available, run the demo against `google-gla:gemini-3-flash-preview` and confirm the three-agent pipeline completes all 10 messages.

## Issues

None yet.

## Decisions

### Decision: Multi-agent orchestration style
- **Options**: A) one supervising agent delegating to sub-agents through tools, B) programmatic hand-off between multiple agents in application code, C) graph-based workflow with `pydantic_graph`
- **Chosen**: B) programmatic hand-off between multiple agents in application code
- **Rationale**: The requested flow is linear and stateful around SQLite persistence. Programmatic hand-off is the simplest Pydantic AI multi-agent pattern for a deterministic three-stage pipeline while still using separate agents and structured outputs.

### Decision: Persistence boundary
- **Options**: A) let the librarian agent call database-writing tools directly, B) have the librarian agent return structured persistence instructions that application code writes to SQLite
- **Chosen**: B) librarian returns structured persistence instructions
- **Rationale**: This keeps side effects deterministic and testable while preserving the librarian as a real agentic decision point.
