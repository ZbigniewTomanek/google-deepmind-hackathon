# Task 01: Scaffold The `benchmarks/` Package And Repo Wiring

Dependencies: None

## Objective

Create the repository structure and shared foundations for the Stage 1 harness without implementing benchmark logic yet.

## Required Changes

- Create the `benchmarks/` tree described in the README.
- Add `__init__.py` files and the `python -m benchmarks` entrypoint.
- Add `benchmarks/models.py` with the shared Pydantic models needed by later tasks.
- Add `benchmarks/README.md` as operator-facing docs stub.
- Add empty placeholder directories and `.gitkeep` files for datasets and reports.
- Update `.gitignore` for benchmark datasets and benchmark result outputs.
- Update `pyproject.toml` only as needed for Stage 1 dependencies and developer ergonomics.

## Constraints

- Keep all benchmarking code outside `src/neocortex/`.
- Do not add benchmark logic that depends on dataset parsing or NeoCortex transport behavior yet.
- Do not create fake APIs that later tasks will need to rewrite entirely.

## Verification

- `uv run python -c "import benchmarks; print('ok')"`
- `uv run python -c "from benchmarks.models import BenchmarkQuestion, QuestionResult; print('ok')"`
- `uv run ruff check benchmarks`

## Completion Rule

Mark this task complete only when the package imports cleanly, the directory tree exists on disk, and later tasks can start editing files in place without structural churn.
