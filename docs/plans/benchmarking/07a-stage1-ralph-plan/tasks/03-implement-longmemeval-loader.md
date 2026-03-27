# Task 03: Implement The LongMemEval Loader And Normalized Benchmark Models

Dependencies: 01, 02

## Objective

Normalize the cleaned LongMemEval-S dataset into internal models that preserve category mapping, answer normalization, and temporal metadata needed by the benchmark runner.

## Required Changes

- Add `benchmarks/benchmarks/longmemeval.py`.
- Parse the official cleaned dataset fields into internal models.
- Map raw `question_type` values to benchmark categories and detect abstention by the `_abs` suffix.
- Preserve `question_date`, `haystack_dates`, `haystack_session_ids`, and answer-session provenance.
- Normalize mixed-type answers into a stable internal representation.
- Add a small local test fixture dataset and loader tests under `benchmarks/tests/`.

## Constraints

- Do not silently discard temporal metadata.
- Do not load the full 500-question haystack into memory if a helper can operate per question.
- Keep the loader faithful to the canonical dataset format rather than inventing a new dataset schema.

## Verification

- `uv run python -c "from benchmarks.benchmarks.longmemeval import load_questions; qs = load_questions(); print(len(qs))"`
- `uv run python -c "from benchmarks.benchmarks.longmemeval import load_questions, get_category_distribution; print(get_category_distribution(load_questions()))"`
- `uv run pytest benchmarks/tests -k longmemeval -v`
- `uv run ruff check benchmarks/benchmarks benchmarks/tests`

## Completion Rule

Mark this task complete only when the loader can parse the real dataset, the tests cover abstention and timestamp handling, and later tasks can consume per-question sessions without extra schema work.
