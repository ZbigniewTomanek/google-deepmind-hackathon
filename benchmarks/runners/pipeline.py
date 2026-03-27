"""Resumable Stage 1 benchmark runner with per-question isolation."""

from __future__ import annotations

import argparse
import asyncio
import os
import re
import subprocess
import time
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from benchmarks.adapters.neocortex_adapter import NeoCortexAdapter, NeoCortexConfig
from benchmarks.benchmarks.longmemeval import (
    LONGMEMEVAL_S_LOCK,
    load_questions,
    load_sessions_for_question,
    longmemeval_dataset_path,
)
from benchmarks.judges.llm_judge import JudgeConfig, JudgeModelName, LLMJudge
from benchmarks.models import BenchmarkQuestion, BenchmarkSummary, CategoryScore, QuestionCategory, QuestionResult
from benchmarks.reports.generator import generate_run_reports
from benchmarks.runners.checkpoint import (
    CheckpointStore,
    QuestionCheckpoint,
    QuestionRunStatus,
    RunCheckpoint,
    RunSummaryInputs,
)
from neocortex.mcp_settings import MCPSettings
from neocortex.services import ServiceContext, create_services, shutdown_services

_STOPWORDS = {
    "a",
    "after",
    "all",
    "an",
    "and",
    "are",
    "be",
    "came",
    "current",
    "did",
    "does",
    "for",
    "has",
    "how",
    "in",
    "is",
    "it",
    "like",
    "many",
    "of",
    "recipe",
    "should",
    "suggest",
    "suggested",
    "the",
    "their",
    "this",
    "user",
    "was",
    "what",
    "which",
    "with",
}
_TOKEN_RE = re.compile(r"[a-z0-9']+")


def _default_results_root() -> Path:
    return Path(__file__).resolve().parents[1] / "reports" / "results"


class PipelineModelConfig(BaseModel):
    """Separate answer-generation and evaluation model settings."""

    answer_model: str = Field(default="mock")
    judge_model: JudgeModelName = Field(default="mock")


class PipelineCLIConfig(BaseModel):
    """Runtime configuration for the Stage 1 benchmark runner."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    benchmark: str = Field(default="longmemeval")
    transport: str = Field(default="direct")
    run_id: str = Field(default="dev")
    limit: int | None = None
    question_ids: list[str] = Field(default_factory=list)
    resume: bool = False
    mock_db: bool = False
    dataset_path: Path | None = None
    results_root: Path = Field(default_factory=_default_results_root)
    models: PipelineModelConfig = Field(default_factory=PipelineModelConfig)


class AnswerGeneratorConfig(BaseModel):
    """Configuration for answer generation in the benchmark loop."""

    model: str = "mock"
    temperature: float = 0.0
    max_tokens: int = 300
    timeout_seconds: float = 60.0
    openai_api_key_env: str = "OPENAI_API_KEY"
    openai_base_url: str | None = None


class AnswerGenerator:
    """Generate benchmark answers from retrieved memory context."""

    def __init__(self, config: AnswerGeneratorConfig) -> None:
        self._config = config
        self._client: object | None = None

    async def initialize(self) -> None:
        """Initialize the OpenAI client when a real answer model is configured."""

        if self._config.model == "mock":
            return

        try:
            from openai import AsyncOpenAI
        except ImportError as exc:
            raise RuntimeError(
                "OpenAI answer generation requires the `openai` package. "
                "Install project dependencies before using a real answer model."
            ) from exc

        api_key = os.getenv(self._config.openai_api_key_env)
        if not api_key:
            raise RuntimeError(
                f"Environment variable {self._config.openai_api_key_env} is required "
                "to use a real benchmark answer model."
            )

        self._client = AsyncOpenAI(api_key=api_key, base_url=self._config.openai_base_url)

    async def generate(self, question: BenchmarkQuestion, retrieved_context: list[str]) -> str:
        """Generate one answer from retrieved benchmark context."""

        if self._config.model == "mock":
            return _mock_answer(question, retrieved_context)
        return await self._generate_with_openai(question, retrieved_context)

    async def _generate_with_openai(self, question: BenchmarkQuestion, retrieved_context: list[str]) -> str:
        try:
            from openai import AsyncOpenAI
        except ImportError as exc:
            raise RuntimeError(
                "OpenAI answer generation requires the `openai` package. "
                "Install project dependencies before using a real answer model."
            ) from exc

        if self._client is None:
            await self.initialize()

        if not isinstance(self._client, AsyncOpenAI):
            raise RuntimeError("OpenAI answer client failed to initialize correctly.")

        context_block = "\n\n".join(
            f"Memory {index + 1}:\n{context}" for index, context in enumerate(retrieved_context)
        ).strip()
        if not context_block:
            context_block = "No relevant memories were retrieved."

        prompt = (
            "Answer the memory question using only the retrieved memories. "
            "If the memories do not contain the answer, say that the information is not available.\n\n"
            f"Question: {question.question}\n\n"
            f"Retrieved memories:\n{context_block}\n\n"
            "Answer:"
        )

        response = await self._client.chat.completions.create(
            model=self._config.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=self._config.temperature,
            max_tokens=self._config.max_tokens,
            timeout=self._config.timeout_seconds,
        )
        message = response.choices[0].message.content
        if isinstance(message, str):
            return message.strip()
        return ""


def build_parser() -> argparse.ArgumentParser:
    """Create the CLI parser for benchmark pipeline execution."""

    parser = argparse.ArgumentParser(
        prog="python -m benchmarks.runners.pipeline",
        description="Run the NeoCortex Stage 1 benchmark pipeline.",
    )
    parser.add_argument("--benchmark", default="longmemeval")
    parser.add_argument("--transport", default="direct")
    parser.add_argument("--run-id", default="dev")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--question-id", dest="question_ids", action="append", default=None)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--mock-db", action="store_true")
    parser.add_argument("--answer-model", default="mock")
    parser.add_argument(
        "--judge-model",
        choices=("gpt-4o", "gpt-4o-mini", "mock"),
        default="mock",
    )
    return parser


def parse_args(argv: Sequence[str] | None = None) -> PipelineCLIConfig:
    """Parse CLI arguments into a structured config object."""

    namespace = build_parser().parse_args(argv)
    return PipelineCLIConfig(
        benchmark=namespace.benchmark,
        transport=namespace.transport,
        run_id=namespace.run_id,
        limit=namespace.limit,
        question_ids=list(namespace.question_ids or []),
        resume=namespace.resume,
        mock_db=namespace.mock_db,
        models=PipelineModelConfig(
            answer_model=namespace.answer_model,
            judge_model=namespace.judge_model,
        ),
    )


async def run_pipeline(config: PipelineCLIConfig) -> RunSummaryInputs:
    """Execute a benchmark run and persist resumable artifacts."""

    _validate_config(config)
    dataset_path = config.dataset_path or longmemeval_dataset_path()
    questions = _select_questions(config, dataset_path)
    checkpoint_store = CheckpointStore(config.results_root, config.run_id)
    checkpoint = _prepare_checkpoint(checkpoint_store, config, questions)
    question_lookup = {question.question_id: question for question in questions}

    pending_questions = [
        question
        for question in questions
        if checkpoint.questions[question.question_id].status != QuestionRunStatus.COMPLETED
    ]
    if not pending_questions:
        summary_inputs = _build_summary_inputs(checkpoint_store, checkpoint, questions)
        _persist_summary_outputs(checkpoint_store, checkpoint, summary_inputs)
        return summary_inputs

    answer_generator = AnswerGenerator(AnswerGeneratorConfig(model=config.models.answer_model))
    judge = LLMJudge(JudgeConfig(model=config.models.judge_model))
    await answer_generator.initialize()
    await judge.initialize()

    service_context: ServiceContext | None = None
    if config.transport == "direct":
        service_context = await create_services(MCPSettings(auth_mode="none", mock_db=config.mock_db))

    try:
        for question in questions:
            if checkpoint.questions[question.question_id].status == QuestionRunStatus.COMPLETED:
                print(f"[resume] skipping completed question {question.question_id}")
                continue

            try:
                await _run_question(
                    question=question,
                    config=config,
                    dataset_path=dataset_path,
                    checkpoint_store=checkpoint_store,
                    checkpoint=checkpoint,
                    answer_generator=answer_generator,
                    judge=judge,
                    service_context=service_context,
                )
            except Exception:
                summary_inputs = _build_summary_inputs(checkpoint_store, checkpoint, questions)
                _persist_summary_outputs(checkpoint_store, checkpoint, summary_inputs)
                raise
            summary_inputs = _build_summary_inputs(checkpoint_store, checkpoint, questions)
            _persist_summary_outputs(checkpoint_store, checkpoint, summary_inputs)
    finally:
        if service_context is not None:
            await shutdown_services(service_context)

    final_summary_inputs = _build_summary_inputs(checkpoint_store, checkpoint, list(question_lookup.values()))
    _persist_summary_outputs(checkpoint_store, checkpoint, final_summary_inputs)
    return final_summary_inputs


async def _run_question(
    *,
    question: BenchmarkQuestion,
    config: PipelineCLIConfig,
    dataset_path: Path,
    checkpoint_store: CheckpointStore,
    checkpoint: RunCheckpoint,
    answer_generator: AnswerGenerator,
    judge: LLMJudge,
    service_context: ServiceContext | None,
) -> None:
    """Execute the full ingest-search-answer-evaluate loop for one question."""

    checkpoint_store.mark_question_running(checkpoint, question.question_id)
    adapter = _build_adapter(config, question.question_id, service_context=service_context)

    try:
        await adapter.initialize()
        await adapter.clear()

        sessions = load_sessions_for_question(question.question_id, path=dataset_path)
        ingest_result = await adapter.ingest_sessions(sessions)
        await adapter.await_indexing(ingest_result)

        search_start = time.perf_counter()
        search_results = await _search_with_fallbacks(adapter, question)
        search_latency_ms = (time.perf_counter() - search_start) * 1000
        retrieved_context = [result.content for result in search_results]

        generated_answer = await answer_generator.generate(question, retrieved_context)
        judge_verdict = await judge.evaluate(
            question_id=question.question_id,
            question=question.question,
            expected_answer=question.expected_answer,
            generated_answer=generated_answer,
            category=question.category,
            question_type=question.question_type,
        )

        result = QuestionResult(
            question_id=question.question_id,
            question=question.question,
            question_type=question.question_type,
            category=question.category,
            expected_answer=question.expected_answer,
            retrieved_context=retrieved_context,
            generated_answer=generated_answer,
            judge_verdict=judge_verdict,
            search_latency_ms=search_latency_ms,
            context_tokens=sum(len(context.split()) for context in retrieved_context),
            metadata={
                "run_id": config.run_id,
                "transport": config.transport,
                "answer_model": config.models.answer_model,
                "judge_model": config.models.judge_model,
                "agent_id": adapter.agent_id,
                "question_date": question.question_date,
                "question_timestamp": (
                    question.question_timestamp.isoformat() if question.question_timestamp is not None else None
                ),
                "session_count": len(sessions),
                "episode_ids": ingest_result.episode_ids,
                "ingest_errors": ingest_result.errors,
                "search_result_metadata": [result.metadata for result in search_results],
                "executed_at": datetime.now(UTC).isoformat(),
            },
        )
        result_path = checkpoint_store.save_question_result(question.question_id, result)
        checkpoint_store.mark_question_completed(checkpoint, question.question_id, result_path=result_path)
        print(
            f"[done] {question.question_id} correct={judge_verdict.correct} "
            f"sessions={len(sessions)} retrieved={len(retrieved_context)}"
        )
    except Exception as exc:
        error_result = QuestionResult(
            question_id=question.question_id,
            question=question.question,
            question_type=question.question_type,
            category=question.category,
            expected_answer=question.expected_answer,
            error=str(exc),
            metadata={
                "run_id": config.run_id,
                "transport": config.transport,
                "answer_model": config.models.answer_model,
                "judge_model": config.models.judge_model,
                "agent_id": adapter.agent_id,
                "executed_at": datetime.now(UTC).isoformat(),
            },
        )
        result_path = checkpoint_store.save_question_result(question.question_id, error_result)
        checkpoint_store.mark_question_failed(
            checkpoint,
            question.question_id,
            error=str(exc),
            result_path=result_path,
        )
        raise


def _build_adapter(
    config: PipelineCLIConfig,
    question_id: str,
    *,
    service_context: ServiceContext | None,
) -> NeoCortexAdapter:
    return NeoCortexAdapter(
        NeoCortexConfig(
            transport=config.transport,
            run_id=config.run_id,
            question_id=question_id,
            mock_db=config.mock_db,
        ),
        service_context=service_context,
    )


async def _search_with_fallbacks(adapter: NeoCortexAdapter, question: BenchmarkQuestion) -> list:
    """Search with the raw question first, then keyword fallbacks when needed."""

    queries = [question.question]
    seen = {question.question.casefold()}
    for token in _keyword_candidates(question.question):
        lowered = token.casefold()
        if lowered not in seen:
            queries.append(token)
            seen.add(lowered)

    deduped: list = []
    seen_items: set[tuple[object, str]] = set()
    for query in queries:
        results = await adapter.search(query, limit=10)
        for result in results:
            item_key = (result.metadata.get("item_id"), result.content)
            if item_key in seen_items:
                continue
            deduped.append(result)
            seen_items.add(item_key)
        if deduped:
            return deduped[:10]
    return []


def _keyword_candidates(question_text: str) -> list[str]:
    tokens = [token for token in _TOKEN_RE.findall(question_text.lower()) if token not in _STOPWORDS]
    ordered: list[str] = []
    for token in tokens:
        if len(token) < 3:
            continue
        if token not in ordered:
            ordered.append(token)
    return ordered


def _mock_answer(question: BenchmarkQuestion, retrieved_context: list[str]) -> str:
    """Cheap deterministic answer generator for smoke runs."""

    answer_lines: list[str] = []
    for context in retrieved_context:
        for raw_line in context.splitlines():
            line = raw_line.strip()
            if "[has_answer]" in line:
                answer_lines.append(_strip_role_prefix(line))
        if answer_lines:
            break

    if answer_lines:
        return " ".join(answer_lines).strip()

    if retrieved_context:
        return _strip_role_prefix(retrieved_context[0].splitlines()[-1].strip())

    if question.category == QuestionCategory.ABSTENTION:
        return "I do not know based on the provided memories."
    return "I do not know based on the provided memories."


def _strip_role_prefix(line: str) -> str:
    if ":" not in line:
        return line
    return line.split(":", 1)[1].strip()


def _select_questions(config: PipelineCLIConfig, dataset_path: Path) -> list[BenchmarkQuestion]:
    if config.question_ids:
        requested = set(config.question_ids)
        all_questions = load_questions(path=dataset_path)
        selected = [question for question in all_questions if question.question_id in requested]
        missing = requested - {question.question_id for question in selected}
        if missing:
            raise ValueError(f"Unknown question_id values requested: {', '.join(sorted(missing))}")
    else:
        selected = load_questions(path=dataset_path, limit=config.limit)

    if config.question_ids and config.limit is not None:
        selected = selected[: config.limit]

    if not selected:
        raise ValueError("No benchmark questions selected.")

    return selected


def _prepare_checkpoint(
    store: CheckpointStore,
    config: PipelineCLIConfig,
    questions: list[BenchmarkQuestion],
) -> RunCheckpoint:
    store.ensure_layout()
    existing = store.load()
    question_ids = [question.question_id for question in questions]

    if existing is not None and not config.resume:
        raise FileExistsError(
            f"Run {config.run_id!r} already exists at {store.run_dir}. "
            "Use --resume or choose a new --run-id."
        )

    if existing is not None:
        _validate_resume_compatibility(existing, config, question_ids)
        return existing

    checkpoint = RunCheckpoint(
        run_id=config.run_id,
        benchmark=config.benchmark,
        transport=config.transport,
        answer_model=config.models.answer_model,
        judge_model=config.models.judge_model,
        dataset_version=LONGMEMEVAL_S_LOCK.revision,
        dataset_sha256=LONGMEMEVAL_S_LOCK.sha256,
        neocortex_git_sha=_git_sha(),
        limit=config.limit,
        question_ids=question_ids,
        questions={
            question_id: QuestionCheckpoint(question_id=question_id)
            for question_id in question_ids
        },
    )
    store.save(checkpoint)
    return checkpoint


def _validate_resume_compatibility(
    checkpoint: RunCheckpoint,
    config: PipelineCLIConfig,
    question_ids: list[str],
) -> None:
    if checkpoint.benchmark != config.benchmark:
        raise ValueError("Cannot resume a run with a different benchmark.")
    if checkpoint.transport != config.transport:
        raise ValueError("Cannot resume a run with a different transport.")
    if checkpoint.answer_model != config.models.answer_model:
        raise ValueError("Cannot resume a run with a different answer model.")
    if checkpoint.judge_model != config.models.judge_model:
        raise ValueError("Cannot resume a run with a different judge model.")
    if checkpoint.question_ids != question_ids:
        raise ValueError("Cannot resume a run with a different selected question set.")


def _build_summary_inputs(
    store: CheckpointStore,
    checkpoint: RunCheckpoint,
    questions: list[BenchmarkQuestion],
) -> RunSummaryInputs:
    completed_results: list[QuestionResult] = []
    completed_paths: list[str] = []
    failed_paths: list[str] = []
    pending_question_ids: list[str] = []

    for question_id in checkpoint.question_ids:
        state = checkpoint.questions[question_id]
        if state.status == QuestionRunStatus.COMPLETED and state.result_path is not None:
            path = store.run_dir / state.result_path
            completed_results.append(QuestionResult.model_validate_json(path.read_text(encoding="utf-8")))
            completed_paths.append(state.result_path)
        elif state.status == QuestionRunStatus.FAILED:
            if state.result_path is not None:
                failed_paths.append(state.result_path)
            pending_question_ids.append(question_id)
        else:
            pending_question_ids.append(question_id)

    category_scores = _category_scores(completed_results)
    latencies = sorted(result.search_latency_ms for result in completed_results)
    correct_results = sum(1 for result in completed_results if result.judge_verdict and result.judge_verdict.correct)
    overall_accuracy = correct_results / len(completed_results) if completed_results else 0.0
    avg_context_tokens = (
        sum(result.context_tokens for result in completed_results) / len(completed_results)
        if completed_results
        else 0.0
    )
    total_duration_seconds = max((datetime.now(UTC) - checkpoint.created_at).total_seconds(), 0.0)

    summary = BenchmarkSummary(
        run_id=checkpoint.run_id,
        benchmark=checkpoint.benchmark,
        judge_model=checkpoint.judge_model,
        answer_model=checkpoint.answer_model,
        neocortex_git_sha=checkpoint.neocortex_git_sha,
        dataset_version=checkpoint.dataset_version,
        dataset_sha256=checkpoint.dataset_sha256,
        timestamp=datetime.now(UTC),
        total_questions=len(checkpoint.question_ids),
        overall_accuracy=overall_accuracy,
        category_scores=category_scores,
        latency_p50_ms=_percentile(latencies, 0.50),
        latency_p95_ms=_percentile(latencies, 0.95),
        latency_p99_ms=_percentile(latencies, 0.99),
        avg_context_tokens=avg_context_tokens,
        total_duration_seconds=total_duration_seconds,
        limit=checkpoint.limit,
        transport=checkpoint.transport,
    )

    del questions
    return RunSummaryInputs(
        summary=summary,
        category_scores=category_scores,
        completed_question_result_paths=completed_paths,
        failed_question_result_paths=failed_paths,
        pending_question_ids=pending_question_ids,
    )


def _persist_summary_outputs(
    store: CheckpointStore,
    checkpoint: RunCheckpoint,
    summary_inputs: RunSummaryInputs,
) -> None:
    summary_path = store.save_summary_inputs(summary_inputs)
    checkpoint.summary_inputs_path = str(summary_path.relative_to(store.run_dir))
    generate_run_reports(store.run_dir, summary_inputs)
    store.save(checkpoint)


def _category_scores(results: list[QuestionResult]) -> list[CategoryScore]:
    counts: dict[QuestionCategory, tuple[int, int]] = {}
    for category in QuestionCategory:
        counts[category] = (0, 0)

    for result in results:
        total, correct = counts[result.category]
        verdict_correct = bool(result.judge_verdict and result.judge_verdict.correct)
        counts[result.category] = (total + 1, correct + int(verdict_correct))

    scores: list[CategoryScore] = []
    for category in QuestionCategory:
        total, correct = counts[category]
        accuracy = correct / total if total else 0.0
        scores.append(CategoryScore(category=category, accuracy=accuracy, total=total, correct=correct))
    return scores


def _percentile(sorted_values: list[float], quantile: float) -> float:
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return sorted_values[0]
    index = (len(sorted_values) - 1) * quantile
    lower = int(index)
    upper = min(lower + 1, len(sorted_values) - 1)
    fraction = index - lower
    return sorted_values[lower] + (sorted_values[upper] - sorted_values[lower]) * fraction


def _validate_config(config: PipelineCLIConfig) -> None:
    if config.benchmark != "longmemeval":
        raise ValueError(f"Unsupported benchmark {config.benchmark!r}. Stage 1 only supports 'longmemeval'.")
    if config.transport != "direct":
        raise ValueError(
            "Stage 1 benchmark-scored LongMemEval runs must use --transport direct. "
            "MCP and REST are smoke/integration transports only in Stage 1."
        )


def _git_sha() -> str:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return "unknown"
    return completed.stdout.strip() or "unknown"


def main(argv: Sequence[str] | None = None) -> int:
    """Run the benchmark pipeline CLI."""

    config = parse_args(argv)
    try:
        summary_inputs = asyncio.run(run_pipeline(config))
    except Exception as exc:
        print(f"Benchmark run failed: {exc}")
        return 1

    summary = summary_inputs.summary
    print(
        "Benchmark run complete. "
        f"run_id={summary.run_id} total={summary.total_questions} "
        f"completed={len(summary_inputs.completed_question_result_paths)} "
        f"pending={len(summary_inputs.pending_question_ids)} "
        f"accuracy={summary.overall_accuracy:.3f}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
