"""Tests for benchmark judge helpers and prompt routing."""

from __future__ import annotations

import pytest

from benchmarks.judges import JudgeConfig, LLMJudge, build_judge_prompt, compute_f1
from benchmarks.models import QuestionCategory


def test_build_judge_prompt_uses_default_template() -> None:
    prompt = build_judge_prompt(
        question="What tea does the user like?",
        answer="oolong",
        response="The user likes oolong tea.",
        category=QuestionCategory.INFORMATION_EXTRACTION,
        question_type="single-session-user",
    )

    assert "Correct Answer: oolong" in prompt
    assert "Rubric:" not in prompt
    assert "off-by-one errors" not in prompt


def test_build_judge_prompt_uses_temporal_template() -> None:
    prompt = build_judge_prompt(
        question="How many days later did the meeting happen?",
        answer="18 days",
        response="19 days later.",
        category=QuestionCategory.TEMPORAL_REASONING,
        question_type="temporal-reasoning",
    )

    assert "off-by-one errors" in prompt


def test_build_judge_prompt_uses_knowledge_update_template() -> None:
    prompt = build_judge_prompt(
        question="What is the user's current title?",
        answer="staff engineer",
        response="They were a software engineer and are now staff engineer.",
        category=QuestionCategory.KNOWLEDGE_UPDATES,
        question_type="knowledge-update",
    )

    assert "updated answer" in prompt


def test_build_judge_prompt_uses_preference_template() -> None:
    prompt = build_judge_prompt(
        question="What should be recommended?",
        answer="Recommend advanced Premiere Pro guides.",
        response="Advanced Premiere Pro guides would fit.",
        category=QuestionCategory.INFORMATION_EXTRACTION,
        question_type="single-session-preference",
    )

    assert "Rubric:" in prompt
    assert "Correct Answer:" not in prompt


def test_build_judge_prompt_uses_abstention_template() -> None:
    prompt = build_judge_prompt(
        question="What is the user's hamster called?",
        answer="The conversation never mentions a hamster.",
        response="I don't know based on the conversation.",
        category=QuestionCategory.ABSTENTION,
        question_type="single-session-user",
    )

    assert "unanswerable question" in prompt
    assert "Explanation:" in prompt


def test_compute_f1_exact_match() -> None:
    assert compute_f1("the answer is blue", "the answer is blue") == 1.0


def test_compute_f1_partial_match() -> None:
    score = compute_f1("blue", "the answer is blue")

    assert 0.0 < score < 1.0


def test_compute_f1_no_match() -> None:
    assert compute_f1("completely wrong", "the right answer") == 0.0


def test_compute_f1_empty_inputs() -> None:
    assert compute_f1("", "") == 1.0
    assert compute_f1("something", "") == 0.0
    assert compute_f1("", "something") == 0.0


@pytest.mark.asyncio
async def test_mock_judge_accepts_matching_answer() -> None:
    judge = LLMJudge(JudgeConfig(model="mock"))
    await judge.initialize()

    verdict = await judge.evaluate(
        question_id="q_user",
        question="What tea does the user like?",
        expected_answer="oolong",
        generated_answer="The user likes oolong tea.",
        category=QuestionCategory.INFORMATION_EXTRACTION,
        question_type="single-session-user",
    )

    assert verdict.question_id == "q_user"
    assert verdict.correct is True
    assert verdict.explanation.startswith("mock:")


@pytest.mark.asyncio
async def test_mock_judge_rejects_wrong_answer() -> None:
    judge = LLMJudge(JudgeConfig(model="mock"))
    await judge.initialize()

    verdict = await judge.evaluate(
        question="What tea does the user like?",
        expected_answer="oolong",
        generated_answer="The user likes coffee.",
        category=QuestionCategory.INFORMATION_EXTRACTION,
        question_type="single-session-user",
    )

    assert verdict.correct is False


@pytest.mark.asyncio
async def test_mock_judge_handles_abstention() -> None:
    judge = LLMJudge(JudgeConfig(model="mock"))
    await judge.initialize()

    verdict = await judge.evaluate(
        question="What is the user's hamster called?",
        expected_answer="This was not mentioned in the conversation.",
        generated_answer="I don't know. That was not mentioned.",
        category=QuestionCategory.ABSTENTION,
        question_type="single-session-user",
    )

    assert verdict.correct is True
