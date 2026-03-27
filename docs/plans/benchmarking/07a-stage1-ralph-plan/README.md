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
| 02 | Add the LongMemEval downloader and dataset lock | 🔴 Not Started | 01 | Version-pin the cleaned dataset and record the verified SHA256. |
| 03 | Implement the LongMemEval loader and normalized benchmark models | 🔴 Not Started | 01, 02 | Parse question/session data, categories, timestamps, and test fixtures. |
| 04 | Implement judges and answer-model configuration | 🔴 Not Started | 01, 03 | Add LongMemEval-compatible judge prompts, mock judge, and F1 scorer. |
| 05 | Implement the direct NeoCortex adapter with question isolation | 🔴 Not Started | 01, 03 | Preserve current NeoCortex ingest/recall semantics, including embeddings. |
| 06 | Implement run-state checkpointing and the per-question pipeline runner | 🔴 Not Started | 03, 04, 05 | Resume by question, not by a contaminated global corpus. |
| 07 | Implement report generation and diagnostic outputs | 🔴 Not Started | 06 | Emit summary, markdown report, and failures JSONL from completed question results. |
| 08 | Add MCP and REST smoke transports plus isolated benchmark DB compose | 🔴 Not Started | 05, 06 | Smoke and integration only, not the primary scored path. |
| 09 | Add end-to-end tests and benchmark operator docs | 🔴 Not Started | 07, 08 | Finish with smoke coverage and clear run instructions. |

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
