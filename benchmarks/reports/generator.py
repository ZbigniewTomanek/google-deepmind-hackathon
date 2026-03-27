"""Stable report generation for benchmark run artifacts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from benchmarks.benchmarks.longmemeval import LONGMEMEVAL_S_LOCK
from benchmarks.models import CategoryScore, QuestionResult
from benchmarks.runners.checkpoint import RunSummaryInputs

SUMMARY_FILENAME = "summary.json"
REPORT_FILENAME = "report.md"
FAILURES_FILENAME = "failures.jsonl"


def generate_run_reports(run_dir: Path, summary_inputs: RunSummaryInputs) -> dict[str, Path]:
    """Write the stable report artifacts for one benchmark run."""

    run_dir.mkdir(parents=True, exist_ok=True)
    completed_results = _load_results(run_dir, summary_inputs.completed_question_result_paths)
    failed_results = _load_results(run_dir, summary_inputs.failed_question_result_paths)
    failure_records = _failure_records(completed_results, failed_results)

    summary_path = run_dir / SUMMARY_FILENAME
    report_path = run_dir / REPORT_FILENAME
    failures_path = run_dir / FAILURES_FILENAME

    summary_path.write_text(
        json.dumps(
            _summary_payload(summary_inputs, completed_results, failed_results, failure_records),
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    report_path.write_text(
        _render_markdown_report(summary_inputs, completed_results, failed_results, failure_records),
        encoding="utf-8",
    )
    failures_path.write_text(_render_failures_jsonl(failure_records), encoding="utf-8")

    return {
        "summary": summary_path,
        "report": report_path,
        "failures": failures_path,
    }


def _load_results(run_dir: Path, relative_paths: list[str]) -> list[QuestionResult]:
    results: list[QuestionResult] = []
    for relative_path in relative_paths:
        path = run_dir / relative_path
        results.append(QuestionResult.model_validate_json(path.read_text(encoding="utf-8")))
    return results


def _summary_payload(
    summary_inputs: RunSummaryInputs,
    completed_results: list[QuestionResult],
    failed_results: list[QuestionResult],
    failure_records: list[dict[str, Any]],
) -> dict[str, Any]:
    summary = summary_inputs.summary
    incorrect_answers = sum(
        1
        for result in completed_results
        if result.judge_verdict is not None and not result.judge_verdict.correct
    )

    return {
        "run_id": summary.run_id,
        "benchmark": summary.benchmark,
        "run_status": "complete" if not summary_inputs.pending_question_ids else "partial",
        "generated_at": summary_inputs.generated_at.isoformat(),
        "timestamp": summary.timestamp.isoformat(),
        "transport": summary.transport,
        "answer_model": summary.answer_model,
        "judge_model": summary.judge_model,
        "dataset": {
            "id": _dataset_id(summary.benchmark),
            "version": summary.dataset_version,
            "sha256": summary.dataset_sha256,
        },
        "neocortex": {
            "git_sha": summary.neocortex_git_sha,
        },
        "questions": {
            "total": summary.total_questions,
            "completed": len(completed_results),
            "incorrect_answers": incorrect_answers,
            "failed_executions": len(failed_results),
            "pending": len(summary_inputs.pending_question_ids),
            "pending_question_ids": summary_inputs.pending_question_ids,
        },
        "metrics": {
            "overall_accuracy": summary.overall_accuracy,
            "avg_context_tokens": summary.avg_context_tokens,
            "total_duration_seconds": summary.total_duration_seconds,
            "latency_ms": {
                "p50": summary.latency_p50_ms,
                "p95": summary.latency_p95_ms,
                "p99": summary.latency_p99_ms,
            },
        },
        "category_scores": [_category_score_payload(score) for score in summary.category_scores],
        "failures_recorded": len(failure_records),
        "limit": summary.limit,
    }


def _dataset_id(benchmark: str) -> str:
    if benchmark == "longmemeval":
        return LONGMEMEVAL_S_LOCK.dataset_id
    return benchmark


def _category_score_payload(score: CategoryScore) -> dict[str, Any]:
    return {
        "category": score.category.value,
        "accuracy": score.accuracy,
        "total": score.total,
        "correct": score.correct,
    }


def _failure_records(
    completed_results: list[QuestionResult],
    failed_results: list[QuestionResult],
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []

    for result in completed_results:
        if result.judge_verdict is None or result.judge_verdict.correct:
            continue
        records.append(_failure_record("incorrect_answer", result))

    for result in failed_results:
        records.append(_failure_record("execution_error", result))

    return records


def _failure_record(failure_type: str, result: QuestionResult) -> dict[str, Any]:
    return {
        "failure_type": failure_type,
        "question_id": result.question_id,
        "category": result.category.value,
        "question_type": result.question_type,
        "question": result.question,
        "expected_answer": result.expected_answer,
        "generated_answer": result.generated_answer,
        "judge": (
            None
            if result.judge_verdict is None
            else {
                "correct": result.judge_verdict.correct,
                "explanation": result.judge_verdict.explanation,
            }
        ),
        "error": result.error,
        "search_latency_ms": result.search_latency_ms,
        "context_tokens": result.context_tokens,
        "retrieved_context": result.retrieved_context,
        "retrieval_provenance": result.metadata.get("search_result_metadata", []),
        "metadata": result.metadata,
    }


def _render_failures_jsonl(failure_records: list[dict[str, Any]]) -> str:
    if not failure_records:
        return ""
    return "\n".join(json.dumps(record, sort_keys=True) for record in failure_records) + "\n"


def _render_markdown_report(
    summary_inputs: RunSummaryInputs,
    completed_results: list[QuestionResult],
    failed_results: list[QuestionResult],
    failure_records: list[dict[str, Any]],
) -> str:
    summary = summary_inputs.summary
    incorrect_answers = sum(
        1
        for result in completed_results
        if result.judge_verdict is not None and not result.judge_verdict.correct
    )
    lines = [
        "# Benchmark Report",
        "",
        "## Run",
        f"- Run ID: `{summary.run_id}`",
        f"- Status: {'complete' if not summary_inputs.pending_question_ids else 'partial'}",
        f"- Benchmark: `{summary.benchmark}`",
        f"- Transport: `{summary.transport}`",
        f"- Answer model: `{summary.answer_model}`",
        f"- Judge model: `{summary.judge_model}`",
        f"- Dataset: `{_dataset_id(summary.benchmark)}` @ `{summary.dataset_version}`",
        f"- Dataset SHA256: `{summary.dataset_sha256}`",
        f"- NeoCortex git SHA: `{summary.neocortex_git_sha}`",
        f"- Generated at: `{summary_inputs.generated_at.isoformat()}`",
    ]

    if summary.limit is not None:
        lines.append(f"- Question limit: `{summary.limit}`")

    lines.extend(
        [
            "",
            "## Metrics",
            f"- Questions completed: `{len(completed_results)}/{summary.total_questions}`",
            f"- Incorrect answers: `{incorrect_answers}`",
            f"- Failed executions: `{len(failed_results)}`",
            f"- Pending questions: `{len(summary_inputs.pending_question_ids)}`",
            f"- Overall accuracy: `{summary.overall_accuracy:.3f}`",
            f"- Avg context tokens: `{summary.avg_context_tokens:.1f}`",
            f"- Runtime seconds: `{summary.total_duration_seconds:.2f}`",
            (
                f"- Latency p50/p95/p99 ms: `{summary.latency_p50_ms:.2f}` / "
                f"`{summary.latency_p95_ms:.2f}` / `{summary.latency_p99_ms:.2f}`"
            ),
            "",
            "## Category Accuracy",
            "| Category | Accuracy | Correct | Total |",
            "| --- | ---: | ---: | ---: |",
        ]
    )

    for score in summary.category_scores:
        lines.append(
            f"| `{score.category.value}` | `{score.accuracy:.3f}` | `{score.correct}` | `{score.total}` |"
        )

    lines.extend(["", "## Failures"])
    if not failure_records:
        lines.append("No incorrect answers or execution failures were recorded.")
    else:
        lines.append(
            f"`failures.jsonl` contains `{len(failure_records)}` machine-readable diagnostic record(s)."
        )
        for failure in failure_records:
            lines.extend(
                [
                    "",
                    f"### `{failure['question_id']}`",
                    f"- Failure type: `{failure['failure_type']}`",
                    f"- Category: `{failure['category']}`",
                    f"- Question: {failure['question']}",
                    f"- Expected answer: `{failure['expected_answer']}`",
                ]
            )
            if failure["generated_answer"]:
                lines.append(f"- Generated answer: `{failure['generated_answer']}`")
            if failure["judge"] is not None:
                lines.append(f"- Judge explanation: `{failure['judge']['explanation']}`")
            if failure["error"]:
                lines.append(f"- Error: `{failure['error']}`")
            lines.append(f"- Retrieved contexts: `{len(failure['retrieved_context'])}`")
            lines.append(f"- Retrieval provenance records: `{len(failure['retrieval_provenance'])}`")

    return "\n".join(lines) + "\n"
