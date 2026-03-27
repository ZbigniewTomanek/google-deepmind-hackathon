"""Persistent checkpoint helpers for resumable benchmark runs."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, Field

from benchmarks.models import BenchmarkSummary, CategoryScore


def utc_now() -> datetime:
    """Return a timezone-aware timestamp for persisted runner state."""

    return datetime.now(UTC)


class QuestionRunStatus(StrEnum):
    """Per-question execution status inside a benchmark run."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class QuestionCheckpoint(BaseModel):
    """Execution checkpoint for a single benchmark question."""

    question_id: str
    status: QuestionRunStatus = QuestionRunStatus.PENDING
    attempts: int = 0
    result_path: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error: str | None = None


class RunCheckpoint(BaseModel):
    """Persisted run metadata plus per-question execution state."""

    run_id: str
    benchmark: str
    transport: str
    answer_model: str
    judge_model: str
    dataset_version: str
    dataset_sha256: str
    neocortex_git_sha: str
    limit: int | None = None
    question_ids: list[str] = Field(default_factory=list)
    questions: dict[str, QuestionCheckpoint] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    summary_inputs_path: str | None = None


class RunSummaryInputs(BaseModel):
    """Aggregated inputs for later report generation."""

    summary: BenchmarkSummary
    category_scores: list[CategoryScore] = Field(default_factory=list)
    completed_question_result_paths: list[str] = Field(default_factory=list)
    failed_question_result_paths: list[str] = Field(default_factory=list)
    pending_question_ids: list[str] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=utc_now)


class CheckpointStore:
    """Filesystem-backed store for runner checkpoints and result paths."""

    def __init__(self, results_root: Path, run_id: str) -> None:
        self.run_dir = results_root / run_id
        self.questions_dir = self.run_dir / "questions"
        self.state_path = self.run_dir / "run_state.json"
        self.summary_inputs_path = self.run_dir / "summary_inputs.json"

    def ensure_layout(self) -> None:
        """Create the run artifact directories if they do not exist yet."""

        self.questions_dir.mkdir(parents=True, exist_ok=True)

    def load(self) -> RunCheckpoint | None:
        """Load an existing checkpoint file if it exists."""

        if not self.state_path.exists():
            return None
        return RunCheckpoint.model_validate_json(self.state_path.read_text(encoding="utf-8"))

    def save(self, checkpoint: RunCheckpoint) -> None:
        """Persist the latest run checkpoint."""

        checkpoint.updated_at = utc_now()
        self.ensure_layout()
        self.state_path.write_text(checkpoint.model_dump_json(indent=2), encoding="utf-8")

    def question_result_path(self, question_id: str) -> Path:
        """Return the canonical per-question result artifact path."""

        return self.questions_dir / f"{question_id}.json"

    def save_question_result(self, question_id: str, payload: BaseModel) -> Path:
        """Persist one per-question result artifact."""

        path = self.question_result_path(question_id)
        self.ensure_layout()
        path.write_text(payload.model_dump_json(indent=2), encoding="utf-8")
        return path

    def save_summary_inputs(self, payload: RunSummaryInputs) -> Path:
        """Persist aggregated summary inputs for the current run."""

        self.ensure_layout()
        self.summary_inputs_path.write_text(payload.model_dump_json(indent=2), encoding="utf-8")
        return self.summary_inputs_path

    def mark_question_running(self, checkpoint: RunCheckpoint, question_id: str) -> None:
        """Mark a question as currently executing."""

        state = checkpoint.questions[question_id]
        state.status = QuestionRunStatus.RUNNING
        state.attempts += 1
        state.started_at = utc_now()
        state.completed_at = None
        state.error = None
        self.save(checkpoint)

    def mark_question_completed(
        self,
        checkpoint: RunCheckpoint,
        question_id: str,
        *,
        result_path: Path,
    ) -> None:
        """Mark a question as successfully completed."""

        state = checkpoint.questions[question_id]
        state.status = QuestionRunStatus.COMPLETED
        state.result_path = str(result_path.relative_to(self.run_dir))
        state.completed_at = utc_now()
        state.error = None
        self.save(checkpoint)

    def mark_question_failed(
        self,
        checkpoint: RunCheckpoint,
        question_id: str,
        *,
        error: str,
        result_path: Path | None = None,
    ) -> None:
        """Mark a question as failed so resume can retry it later."""

        state = checkpoint.questions[question_id]
        state.status = QuestionRunStatus.FAILED
        state.error = error
        state.completed_at = None
        if result_path is not None:
            state.result_path = str(result_path.relative_to(self.run_dir))
        self.save(checkpoint)
