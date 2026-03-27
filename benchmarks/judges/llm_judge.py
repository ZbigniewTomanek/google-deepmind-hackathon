"""LongMemEval-style answer judges with mock and OpenAI-backed implementations."""

from __future__ import annotations

import os
import re
from collections.abc import Awaitable, Callable
from typing import Literal

from pydantic import BaseModel

from benchmarks.judges.f1_judge import compute_f1, normalize_text
from benchmarks.models import JudgeVerdict, QuestionCategory

JudgeModelName = Literal["gpt-4o", "gpt-4o-mini", "mock"]

_DEFAULT_PROMPT_TEMPLATE = (
    "I will give you a question, a correct answer, and a response from a model. "
    "Please answer yes if the response contains the correct answer. Otherwise, answer no. "
    "If the response is equivalent to the correct answer or contains all the intermediate "
    "steps to get the correct answer, you should also answer yes. If the response only "
    "contains a subset of the information required by the answer, answer no.\n\n"
    "Question: {question}\n\n"
    "Correct Answer: {answer}\n\n"
    "Model Response: {response}\n\n"
    "Is the model response correct? Answer yes or no only."
)
_TEMPORAL_PROMPT_TEMPLATE = (
    "I will give you a question, a correct answer, and a response from a model. "
    "Please answer yes if the response contains the correct answer. Otherwise, answer no. "
    "If the response is equivalent to the correct answer or contains all the intermediate "
    "steps to get the correct answer, you should also answer yes. If the response only "
    "contains a subset of the information required by the answer, answer no. In addition, "
    "do not penalize off-by-one errors for the number of days. If the question asks for the "
    "number of days/weeks/months, etc., and the model makes off-by-one errors (e.g., "
    "predicting 19 days when the answer is 18), the model's response is still correct.\n\n"
    "Question: {question}\n\n"
    "Correct Answer: {answer}\n\n"
    "Model Response: {response}\n\n"
    "Is the model response correct? Answer yes or no only."
)
_KNOWLEDGE_UPDATE_PROMPT_TEMPLATE = (
    "I will give you a question, a correct answer, and a response from a model. "
    "Please answer yes if the response contains the correct answer. Otherwise, answer no. "
    "If the response contains some previous information along with an updated answer, the "
    "response should be considered as correct as long as the updated answer is the required "
    "answer.\n\n"
    "Question: {question}\n\n"
    "Correct Answer: {answer}\n\n"
    "Model Response: {response}\n\n"
    "Is the model response correct? Answer yes or no only."
)
_PREFERENCE_PROMPT_TEMPLATE = (
    "I will give you a question, a rubric for desired personalized response, and a response "
    "from a model. Please answer yes if the response satisfies the desired response. "
    "Otherwise, answer no. The model does not need to reflect all the points in the rubric. "
    "The response is correct as long as it recalls and utilizes the user's personal "
    "information correctly.\n\n"
    "Question: {question}\n\n"
    "Rubric: {answer}\n\n"
    "Model Response: {response}\n\n"
    "Is the model response correct? Answer yes or no only."
)
_ABSTENTION_PROMPT_TEMPLATE = (
    "I will give you an unanswerable question, an explanation, and a response from a model. "
    "Please answer yes if the model correctly identifies the question as unanswerable. The "
    "model could say that the information is incomplete, or some other information is given "
    "but the asked information is not.\n\n"
    "Question: {question}\n\n"
    "Explanation: {answer}\n\n"
    "Model Response: {response}\n\n"
    "Does the model correctly identify the question as unanswerable? Answer yes or no only."
)
_YES_NO_RE = re.compile(r"\b(yes|no)\b", re.IGNORECASE)
_ABSTENTION_MARKERS = (
    "dont know",
    "do not know",
    "not mentioned",
    "not provided",
    "not enough information",
    "information is incomplete",
    "unanswerable",
)


class JudgeConfig(BaseModel):
    """Configuration for a benchmark judge model."""

    model: JudgeModelName = "gpt-4o"
    temperature: float = 0.0
    max_tokens: int = 10
    timeout_seconds: float = 30.0
    openai_api_key_env: str = "OPENAI_API_KEY"
    openai_base_url: str | None = None


def build_judge_prompt(
    *,
    question: str,
    answer: str,
    response: str,
    category: QuestionCategory,
    question_type: str,
) -> str:
    """Build the category-aware prompt used by the LongMemEval judge."""

    if category == QuestionCategory.ABSTENTION:
        template = _ABSTENTION_PROMPT_TEMPLATE
    elif question_type == "single-session-preference":
        template = _PREFERENCE_PROMPT_TEMPLATE
    elif category == QuestionCategory.TEMPORAL_REASONING:
        template = _TEMPORAL_PROMPT_TEMPLATE
    elif category == QuestionCategory.KNOWLEDGE_UPDATES:
        template = _KNOWLEDGE_UPDATE_PROMPT_TEMPLATE
    else:
        template = _DEFAULT_PROMPT_TEMPLATE

    return template.format(question=question, answer=answer, response=response)


class LLMJudge:
    """LLM-as-judge wrapper with LongMemEval prompt routing."""

    def __init__(
        self,
        config: JudgeConfig,
        *,
        completion_fn: Callable[[str], Awaitable[str]] | None = None,
    ) -> None:
        self._config = config
        self._completion_fn = completion_fn
        self._client: object | None = None

    async def initialize(self) -> None:
        """Initialize any remote client required by the configured judge."""

        if self._config.model == "mock" or self._completion_fn is not None:
            return

        try:
            from openai import AsyncOpenAI
        except ImportError as exc:
            raise RuntimeError(
                "OpenAI judge support requires the `openai` package. "
                "Install project dependencies before using a real judge model."
            ) from exc

        api_key = os.getenv(self._config.openai_api_key_env)
        if not api_key:
            raise RuntimeError(
                f"Environment variable {self._config.openai_api_key_env} is required "
                "to use the OpenAI benchmark judge."
            )

        self._client = AsyncOpenAI(api_key=api_key, base_url=self._config.openai_base_url)

    async def evaluate(
        self,
        *,
        question_id: str = "",
        question: str,
        expected_answer: str,
        generated_answer: str,
        category: QuestionCategory,
        question_type: str,
    ) -> JudgeVerdict:
        """Evaluate one generated answer against the benchmark reference."""

        if self._config.model == "mock":
            correct, explanation = self._mock_evaluate(
                expected_answer=expected_answer,
                generated_answer=generated_answer,
                category=category,
            )
            return JudgeVerdict(question_id=question_id, correct=correct, explanation=explanation)

        prompt = build_judge_prompt(
            question=question,
            answer=expected_answer,
            response=generated_answer,
            category=category,
            question_type=question_type,
        )
        response_text = await self._complete(prompt)
        return JudgeVerdict(
            question_id=question_id,
            correct=_response_is_yes(response_text),
            explanation=response_text.strip(),
        )

    async def _complete(self, prompt: str) -> str:
        if self._completion_fn is not None:
            return await self._completion_fn(prompt)

        try:
            from openai import AsyncOpenAI
        except ImportError as exc:
            raise RuntimeError(
                "OpenAI judge support requires the `openai` package. "
                "Install project dependencies before using a real judge model."
            ) from exc

        if self._client is None:
            await self.initialize()

        if not isinstance(self._client, AsyncOpenAI):
            raise RuntimeError("OpenAI judge client failed to initialize correctly.")

        response = await self._client.chat.completions.create(
            model=self._config.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=self._config.temperature,
            max_tokens=self._config.max_tokens,
            timeout=self._config.timeout_seconds,
        )

        message = response.choices[0].message.content
        if isinstance(message, str):
            return message
        return ""

    def _mock_evaluate(
        self,
        *,
        expected_answer: str,
        generated_answer: str,
        category: QuestionCategory,
    ) -> tuple[bool, str]:
        """Cheap deterministic smoke-test judge."""

        normalized_generated = normalize_text(generated_answer)
        if category == QuestionCategory.ABSTENTION:
            correct = any(marker in normalized_generated for marker in _ABSTENTION_MARKERS)
            explanation = "mock: abstention detected" if correct else "mock: abstention missing"
            return correct, explanation

        normalized_expected = normalize_text(expected_answer)
        exact_or_contained = bool(normalized_expected) and normalized_expected in normalized_generated
        f1_score = compute_f1(generated_answer, expected_answer)
        correct = exact_or_contained or f1_score >= 0.5
        explanation = f"mock: f1={f1_score:.3f}"
        return correct, explanation


def _response_is_yes(response_text: str) -> bool:
    """Parse the binary verdict expected from the benchmark judge prompt."""

    match = _YES_NO_RE.search(response_text)
    return bool(match and match.group(1).lower() == "yes")
