from __future__ import annotations

import json
from pathlib import Path

import pytest

from benchmarks.runners.checkpoint import CheckpointStore, QuestionRunStatus, RunCheckpoint, RunSummaryInputs
from benchmarks.runners.pipeline import (
    PipelineCLIConfig,
    PipelineModelConfig,
    load_sessions_for_question,
    run_pipeline,
)


@pytest.fixture
def fixture_dataset_path() -> Path:
    return Path(__file__).parent / "fixtures" / "longmemeval_fixture.json"


@pytest.mark.asyncio
async def test_pipeline_run_persists_question_results_and_summary_inputs(
    tmp_path: Path,
    fixture_dataset_path: Path,
) -> None:
    config = PipelineCLIConfig(
        run_id="runner-smoke",
        mock_db=True,
        limit=2,
        dataset_path=fixture_dataset_path,
        results_root=tmp_path,
        models=PipelineModelConfig(answer_model="mock", judge_model="mock"),
    )

    summary_inputs = await run_pipeline(config)
    store = CheckpointStore(tmp_path, "runner-smoke")
    checkpoint = RunCheckpoint.model_validate_json(store.state_path.read_text(encoding="utf-8"))

    assert isinstance(summary_inputs, RunSummaryInputs)
    assert checkpoint.summary_inputs_path == "summary_inputs.json"
    assert checkpoint.questions["q_user"].status == QuestionRunStatus.COMPLETED
    assert checkpoint.questions["q_assistant"].status == QuestionRunStatus.COMPLETED
    assert len(summary_inputs.completed_question_result_paths) == 2
    assert summary_inputs.pending_question_ids == []
    assert store.summary_inputs_path.exists()
    assert store.question_result_path("q_user").exists()
    assert store.question_result_path("q_assistant").exists()
    assert (store.run_dir / "summary.json").exists()
    assert (store.run_dir / "report.md").exists()
    assert (store.run_dir / "failures.jsonl").exists()

    summary_payload = json.loads((store.run_dir / "summary.json").read_text(encoding="utf-8"))
    assert summary_payload["benchmark"] == "longmemeval"
    assert summary_payload["questions"]["completed"] == 2
    assert summary_payload["questions"]["pending"] == 0
    assert summary_payload["dataset"]["id"] == "xiaowu0162/longmemeval-cleaned"


@pytest.mark.asyncio
async def test_pipeline_reports_include_failure_diagnostics(
    tmp_path: Path,
    fixture_dataset_path: Path,
) -> None:
    config = PipelineCLIConfig(
        run_id="runner-report-failures",
        mock_db=True,
        limit=7,
        dataset_path=fixture_dataset_path,
        results_root=tmp_path,
        models=PipelineModelConfig(answer_model="mock", judge_model="mock"),
    )

    await run_pipeline(config)
    store = CheckpointStore(tmp_path, "runner-report-failures")

    summary_payload = json.loads((store.run_dir / "summary.json").read_text(encoding="utf-8"))
    failures_lines = (store.run_dir / "failures.jsonl").read_text(encoding="utf-8").strip().splitlines()
    report_body = (store.run_dir / "report.md").read_text(encoding="utf-8")

    assert summary_payload["failures_recorded"] >= 1
    assert failures_lines

    first_failure = json.loads(failures_lines[0])
    assert first_failure["failure_type"] == "incorrect_answer"
    assert first_failure["retrieval_provenance"]
    assert "failures.jsonl" in report_body


@pytest.mark.asyncio
async def test_pipeline_resume_skips_completed_questions(
    tmp_path: Path,
    fixture_dataset_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    initial_config = PipelineCLIConfig(
        run_id="resume-smoke",
        mock_db=True,
        limit=2,
        dataset_path=fixture_dataset_path,
        results_root=tmp_path,
        models=PipelineModelConfig(answer_model="mock", judge_model="mock"),
    )
    await run_pipeline(initial_config)

    def fail_if_called(*args: object, **kwargs: object) -> None:
        raise AssertionError("load_sessions_for_question should not be called for completed questions")

    monkeypatch.setattr("benchmarks.runners.pipeline.load_sessions_for_question", fail_if_called)

    resumed_summary = await run_pipeline(initial_config.model_copy(update={"resume": True}))
    assert len(resumed_summary.completed_question_result_paths) == 2
    assert resumed_summary.pending_question_ids == []


@pytest.mark.asyncio
async def test_pipeline_resume_retries_failed_question_only(
    tmp_path: Path,
    fixture_dataset_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = PipelineCLIConfig(
        run_id="resume-retry",
        mock_db=True,
        limit=2,
        dataset_path=fixture_dataset_path,
        results_root=tmp_path,
        models=PipelineModelConfig(answer_model="mock", judge_model="mock"),
    )
    original_loader = load_sessions_for_question

    def fail_second_question(question_id: str, *, path: Path):
        if question_id == "q_assistant":
            raise RuntimeError("synthetic loader failure")
        return original_loader(question_id, path=path)

    monkeypatch.setattr("benchmarks.runners.pipeline.load_sessions_for_question", fail_second_question)

    with pytest.raises(RuntimeError, match="synthetic loader failure"):
        await run_pipeline(config)

    store = CheckpointStore(tmp_path, "resume-retry")
    checkpoint = RunCheckpoint.model_validate_json(store.state_path.read_text(encoding="utf-8"))
    assert checkpoint.questions["q_user"].status == QuestionRunStatus.COMPLETED
    assert checkpoint.questions["q_assistant"].status == QuestionRunStatus.FAILED

    resumed_question_ids: list[str] = []

    def recording_loader(question_id: str, *, path: Path):
        resumed_question_ids.append(question_id)
        return original_loader(question_id, path=path)

    monkeypatch.setattr("benchmarks.runners.pipeline.load_sessions_for_question", recording_loader)

    resumed_summary = await run_pipeline(config.model_copy(update={"resume": True}))
    resumed_checkpoint = RunCheckpoint.model_validate_json(store.state_path.read_text(encoding="utf-8"))

    assert resumed_question_ids == ["q_assistant"]
    assert len(resumed_summary.completed_question_result_paths) == 2
    assert resumed_summary.pending_question_ids == []
    assert resumed_checkpoint.questions["q_assistant"].status == QuestionRunStatus.COMPLETED
    assert resumed_checkpoint.questions["q_assistant"].attempts == 2


@pytest.mark.asyncio
async def test_pipeline_rejects_non_direct_transport(
    tmp_path: Path,
    fixture_dataset_path: Path,
) -> None:
    config = PipelineCLIConfig(
        run_id="bad-transport",
        transport="mcp",
        mock_db=True,
        dataset_path=fixture_dataset_path,
        results_root=tmp_path,
        models=PipelineModelConfig(answer_model="mock", judge_model="mock"),
    )

    with pytest.raises(ValueError, match="must use --transport direct"):
        await run_pipeline(config)
