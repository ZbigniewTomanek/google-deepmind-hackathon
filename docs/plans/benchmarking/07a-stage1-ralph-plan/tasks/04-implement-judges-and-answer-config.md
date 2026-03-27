# Task 04: Implement Judges And Answer-Model Configuration

Dependencies: 01, 03

## Objective

Add evaluation components that match LongMemEval’s judging style while separating answer generation from answer evaluation.

## Required Changes

- Add `benchmarks/judges/llm_judge.py`.
- Add `benchmarks/judges/f1_judge.py`.
- Implement LongMemEval-compatible prompt variants for the relevant categories and abstention handling.
- Add a `mock` judge for smoke tests.
- Introduce configuration models that distinguish `judge_model` from `answer_model`.
- Add unit tests for prompt routing, mock behavior, and F1 scoring.

## Constraints

- Do not hardcode answer generation to the judge model.
- Keep prompt behavior aligned with the official benchmark methodology.
- Do not block Stage 1 on adding every provider under the sun. OpenAI plus mock is enough for the first correct implementation, with other providers optional if cleanly supported.

## Verification

- `uv run pytest benchmarks/tests -k 'judge or f1' -v`
- `uv run python -c "from benchmarks.judges.llm_judge import JudgeConfig; print(JudgeConfig(model='mock'))"`
- If API keys are available, run one live judge call on a single real LongMemEval example to confirm client wiring and response parsing.
- `uv run ruff check benchmarks/judges benchmarks/tests`

## Completion Rule

Mark this task complete only when the harness has a working mock judge, a real judge configuration path, and the pipeline can ask for separate answer and judge models.
