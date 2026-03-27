"""Tests for the LongMemEval loader and normalization helpers."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from benchmarks.benchmarks.longmemeval import (
    _normalize_answer,
    get_category_distribution,
    load_questions,
    load_sessions_for_question,
)
from benchmarks.models import QuestionCategory


@pytest.fixture
def fixture_dataset_path() -> Path:
    return Path(__file__).parent / "fixtures" / "longmemeval_fixture.json"


def test_load_questions_parses_fixture(fixture_dataset_path: Path) -> None:
    questions = load_questions(path=fixture_dataset_path)

    assert len(questions) == 7
    assert questions[0].question_id == "q_user"
    assert questions[0].question_timestamp == datetime(2025, 1, 5, 9, 30)
    assert questions[0].haystack_session_ids == ["user_0", "user_1"]
    assert questions[0].haystack_dates == ["2024/12/01 (Sun) 10:00", "2024/12/02 (Mon) 11:00"]


def test_load_questions_honors_limit(fixture_dataset_path: Path) -> None:
    questions = load_questions(path=fixture_dataset_path, limit=3)

    assert [question.question_id for question in questions] == ["q_user", "q_assistant", "q_preference"]


def test_load_questions_normalizes_answers_and_categories(fixture_dataset_path: Path) -> None:
    questions = {question.question_id: question for question in load_questions(path=fixture_dataset_path)}

    assert questions["q_preference"].expected_answer == (
        "Adobe Premiere Pro advanced guides; motion graphics tutorials"
    )
    assert questions["q_multi"].expected_answer == "3"
    assert questions["q_preference"].category == QuestionCategory.INFORMATION_EXTRACTION
    assert questions["q_multi"].category == QuestionCategory.MULTI_SESSION_REASONING
    assert questions["q_temporal"].category == QuestionCategory.TEMPORAL_REASONING
    assert questions["q_update"].category == QuestionCategory.KNOWLEDGE_UPDATES
    assert questions["q_missing_abs"].category == QuestionCategory.ABSTENTION


def test_load_sessions_preserves_timestamps_and_answer_provenance(fixture_dataset_path: Path) -> None:
    sessions = load_sessions_for_question("q_update", path=fixture_dataset_path)

    assert len(sessions) == 2
    assert sessions[0].timestamp == datetime(2024, 8, 1, 10, 0)
    assert sessions[1].timestamp == datetime(2024, 12, 20, 18, 0)
    assert sessions[0].metadata["contains_answer"] is True
    assert sessions[1].metadata["contains_answer"] is True
    assert sessions[1].metadata["haystack_date"] == "2024/12/20 (Fri) 18:00"
    assert sessions[1].messages[0].has_answer is True


def test_load_sessions_for_abstention_question_has_no_answer_session(fixture_dataset_path: Path) -> None:
    sessions = load_sessions_for_question("q_missing_abs", path=fixture_dataset_path)

    assert len(sessions) == 1
    assert sessions[0].metadata["contains_answer"] is False
    assert sessions[0].messages[0].has_answer is False


def test_category_distribution_reports_all_categories(fixture_dataset_path: Path) -> None:
    distribution = get_category_distribution(load_questions(path=fixture_dataset_path))

    assert distribution == {
        "information_extraction": 3,
        "multi_session_reasoning": 1,
        "temporal_reasoning": 1,
        "knowledge_updates": 1,
        "abstention": 1,
    }


def test_normalize_answer_handles_nested_non_string_values() -> None:
    assert _normalize_answer(["alpha", 2, {"k": "v"}]) == 'alpha; 2; {"k": "v"}'
