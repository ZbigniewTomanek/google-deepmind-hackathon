# Stage 1 Benchmarking Ralph Plan

Status: Ready
Supersedes: `docs/plans/benchmarking/07a-stage1-implementation.md`
Primary target: LongMemEval-S on NeoCortex

## Goal

Build a runnable Stage 1 benchmarking harness under `benchmarks/` that can:
- download and lock the cleaned LongMemEval-S dataset,
- run a correct NeoCortex benchmark loop with per-question isolation,
- evaluate answers with a LongMemEval-compatible judge,
- resume interrupted runs,
- emit reproducible reports and diagnostics.

## End Goal

The end goal of Stage 1 is not just to add benchmark code. It is to give NeoCortex a trustworthy LongMemEval-S benchmarking capability that can answer three questions with evidence:

- What score does NeoCortex achieve on a real long-term memory benchmark when run correctly?
- Can that score be reproduced later against newer NeoCortex revisions using the same dataset and method?
- When NeoCortex fails, do we have enough preserved evidence to understand why and improve the system deliberately?

When this plan is complete, an operator should be able to run a single benchmark command, produce believable report artifacts, inspect failures, and use the result as a real baseline for future NeoCortex work.

## Current Repo Facts

- `benchmarks/` does not exist yet.
- NeoCortex exposes three real access paths today: direct protocol via `create_services()`, MCP tools, and ingestion REST.
- Direct protocol is the only path that can be made benchmark-correct in Stage 1 without changing `src/neocortex/`, because MCP and REST derive agent identity from auth context and do not let the harness vary identity per question.
- The real system computes embeddings on write and on recall. A direct benchmark path must preserve that behavior instead of calling `store_episode()` and `recall()` without embeddings.
- `run_ralph_loop.sh` requires a `README.md` with a `Task Status` table and one task file per executable task.

## Corrected Decisions

- Full benchmark-scored runs use `direct` transport only in Stage 1.
- MCP and REST transports remain in Stage 1, but only for smoke and integration coverage.
- Each LongMemEval question must run in an isolated scope keyed by `run_id + question_id`. No cross-question memory sharing is allowed.
- The runner must preserve temporal information from `haystack_dates` and `question_date`.
- Answer generation and judge evaluation are separate knobs. Do not hardcode answer generation to the judge model.
- Resume semantics are per-question, not only per-phase. A partially completed run must skip already completed questions.
- Most task-level verification should avoid paid API calls, but Stage 1 should still include one small paid-model validation run to prove the real benchmark path works end-to-end.

## Deliverables

- `benchmarks/` package with models, adapters, datasets, judges, runner, reports, tests, and docs.
- `benchmarks/download_datasets.py` plus a committed dataset lock file or constant containing the verified LongMemEval-S SHA256.
- `benchmarks/runners/pipeline.py` that can run a limited or full LongMemEval-S benchmark in direct mode and resume safely.
- `benchmarks/reports/results/<run-id>/summary.json`
- `benchmarks/reports/results/<run-id>/report.md`
- `benchmarks/reports/results/<run-id>/failures.jsonl`

## Task Status

| ID | Task | Status | Dependencies | Notes |
| --- | --- | --- | --- | --- |
| 01 | Scaffold the `benchmarks/` package and repo wiring | 🟢 Complete | None | Completed 2026-03-27: tree, gitignore rules, base README, shared models, and CLI scaffolding added. |
| 02 | Add the LongMemEval downloader and dataset lock | 🟢 Complete | 01 | Completed 2026-03-27: pinned the cleaned LongMemEval-S Hugging Face revision, verified SHA256, added skip-or-refresh download flow, and wrote a local manifest. |
| 03 | Implement the LongMemEval loader and normalized benchmark models | 🟢 Complete | 01, 02 | Completed 2026-03-27: added a streaming LongMemEval loader, parsed question and session timestamps, preserved answer-session provenance, and added fixture-backed loader tests. |
| 04 | Implement judges and answer-model configuration | 🟢 Complete | 01, 03 | Completed 2026-03-27: added LongMemEval-style prompt routing, mock and OpenAI judge paths, token-level F1 scoring, separate answer/judge CLI model config, and unit coverage. |
| 05 | Implement the direct NeoCortex adapter with question isolation | 🟢 Complete | 01, 03 | Completed 2026-03-27: added direct adapter lifecycle via `create_services()`, deterministic per-question scope identities, embedding-aware ingest/recall, scoped cleanup, and mock-db isolation tests. |
| 06 | Implement run-state checkpointing and the per-question pipeline runner | 🟢 Complete | 03, 04, 05 | Completed 2026-03-27: added resumable per-question execution, persisted run/question artifacts, direct-only Stage 1 enforcement, and verified clean `--resume` behavior on a mock-db smoke run. |
| 07 | Implement report generation and diagnostic outputs | 🟢 Complete | 06 | Completed 2026-03-27: added stable summary/report/failures artifacts, wired report generation into the resumable runner, and verified mock-run diagnostics plus machine-readable failure records. |
| 08 | Add MCP and REST smoke transports plus isolated benchmark DB compose | 🟢 Complete | 05, 06 | Completed 2026-03-27: wired MCP streamable-HTTP and REST smoke adapters, added smoke coverage against live local HTTP servers, and replaced the placeholder bench compose with isolated `postgres-bench` plus bench-only HTTP service variants using `POSTGRES_DATABASE`. |
| 09 | Add end-to-end tests and benchmark operator docs | 🟢 Complete | 07, 08 | Completed 2026-03-27: added failed-question resume coverage, expanded operator docs with direct-only run instructions and artifact inspection guidance, and verified both mock smoke and 1-question paid-model validation runs. |

## Dependency Notes

- Tasks 01-04 are foundation work.
- Task 05 is the key correctness boundary. Do not start the runner before the adapter preserves production semantics.
- Task 06 must encode the corrected execution model. If it drifts back to “ingest all questions, then query all questions”, the plan is wrong.
- Task 08 is intentionally late because its transport behavior depends on the runner and adapter contracts being stable first.

## Acceptance Criteria

- `uv run python -m benchmarks.runners.pipeline --benchmark longmemeval --transport direct --judge-model mock --answer-model mock --run-id smoke --limit 5 --mock-db` completes successfully.
- The runner isolates each question’s corpus from every other question in the same run.
- A resumed run skips completed questions and continues from the first incomplete question.
- The direct path uses embeddings for writes and query-time recall whenever NeoCortex embeddings are available.
- The operator docs state clearly that Stage 1 benchmark-scored runs use direct transport, while MCP and REST are smoke-only.
- If model API keys are available, a small real-model validation run on 1-3 LongMemEval questions completes successfully and produces normal report artifacts.

## Out Of Scope

- LoCoMo
- ConvoMem
- MemoryBench TypeScript provider
- Changes to `src/neocortex/`
- CI automation
- Advanced retrieval metrics like NDCG unless they fall out naturally from preserved provenance

## External References Used To Correct This Plan

- LongMemEval paper: https://openreview.net/pdf?id=wIonk5yTDq
- Official LongMemEval repo: https://github.com/xiaowu0162/LongMemEval
- Cleaned LongMemEval dataset: https://huggingface.co/datasets/xiaowu0162/longmemeval-cleaned
- MemoryBench README: https://github.com/supermemoryai/memorybench
