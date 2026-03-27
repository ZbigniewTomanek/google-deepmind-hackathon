"""Tests for the benchmark pipeline CLI scaffold."""

from __future__ import annotations

from benchmarks.runners.pipeline import parse_args


def test_pipeline_cli_keeps_answer_and_judge_models_separate() -> None:
    config = parse_args(
        [
            "--benchmark",
            "longmemeval",
            "--transport",
            "direct",
            "--run-id",
            "smoke",
            "--answer-model",
            "gpt-4.1-mini",
            "--judge-model",
            "mock",
            "--question-id",
            "q_user",
            "--question-id",
            "q_assistant",
            "--limit",
            "5",
            "--resume",
            "--mock-db",
        ]
    )

    assert config.benchmark == "longmemeval"
    assert config.transport == "direct"
    assert config.run_id == "smoke"
    assert config.limit == 5
    assert config.question_ids == ["q_user", "q_assistant"]
    assert config.resume is True
    assert config.mock_db is True
    assert config.models.answer_model == "gpt-4.1-mini"
    assert config.models.judge_model == "mock"
