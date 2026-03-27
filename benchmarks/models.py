"""Shared Pydantic models for the benchmarking harness."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class MessageRole(StrEnum):
    """Role for a single conversation turn."""

    USER = "user"
    ASSISTANT = "assistant"


class SessionMessage(BaseModel):
    """A single turn in a benchmark session."""

    role: MessageRole
    content: str
    has_answer: bool = False


class Session(BaseModel):
    """Conversation data ingested for one benchmark session."""

    session_id: str
    messages: list[SessionMessage] = Field(default_factory=list)
    timestamp: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class QuestionCategory(StrEnum):
    """LongMemEval's normalized evaluation categories."""

    INFORMATION_EXTRACTION = "information_extraction"
    MULTI_SESSION_REASONING = "multi_session_reasoning"
    TEMPORAL_REASONING = "temporal_reasoning"
    KNOWLEDGE_UPDATES = "knowledge_updates"
    ABSTENTION = "abstention"


class BenchmarkQuestion(BaseModel):
    """A single normalized benchmark question."""

    question_id: str
    question: str
    question_type: str
    category: QuestionCategory
    expected_answer: str
    question_date: str | None = None
    question_timestamp: datetime | None = None
    answer_session_ids: list[str] = Field(default_factory=list)
    haystack_session_ids: list[str] = Field(default_factory=list)
    haystack_dates: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class IngestResult(BaseModel):
    """Result returned by a benchmark transport ingest step."""

    episode_ids: list[int] = Field(default_factory=list)
    sessions_ingested: int = 0
    errors: list[str] = Field(default_factory=list)


class SearchResult(BaseModel):
    """A single retrieved memory item."""

    content: str
    score: float = 0.0
    source: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class JudgeVerdict(BaseModel):
    """Outcome of evaluating a generated answer."""

    question_id: str
    correct: bool
    explanation: str = ""


class QuestionResult(BaseModel):
    """Full pipeline result for one benchmark question."""

    question_id: str
    question: str
    question_type: str
    category: QuestionCategory
    expected_answer: str
    retrieved_context: list[str] = Field(default_factory=list)
    generated_answer: str = ""
    judge_verdict: JudgeVerdict | None = None
    search_latency_ms: float = 0.0
    context_tokens: int = 0
    error: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class CategoryScore(BaseModel):
    """Aggregated accuracy for a single category."""

    category: QuestionCategory
    accuracy: float
    total: int
    correct: int


class BenchmarkSummary(BaseModel):
    """Top-level run summary for report generation."""

    run_id: str
    benchmark: str
    judge_model: str
    answer_model: str
    neocortex_git_sha: str
    dataset_version: str
    dataset_sha256: str
    timestamp: datetime
    total_questions: int
    overall_accuracy: float
    category_scores: list[CategoryScore] = Field(default_factory=list)
    latency_p50_ms: float = 0.0
    latency_p95_ms: float = 0.0
    latency_p99_ms: float = 0.0
    avg_context_tokens: float = 0.0
    total_duration_seconds: float = 0.0
    limit: int | None = None
    transport: str = "direct"


class PipelinePhase(StrEnum):
    """Named phases in the benchmark pipeline."""

    SETUP = "setup"
    INGEST = "ingest"
    INDEX = "index"
    QUERY = "query"
    ANSWER = "answer"
    EVALUATE = "evaluate"
    REPORT = "report"


class PhaseResult(BaseModel):
    """Checkpoint payload for a completed pipeline phase."""

    phase: PipelinePhase
    completed_at: datetime
    data: dict[str, Any] = Field(default_factory=dict)
