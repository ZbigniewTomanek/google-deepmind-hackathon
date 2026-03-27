# Task 02: Add The LongMemEval Downloader And Dataset Lock

Dependencies: 01

## Objective

Implement a downloader for the cleaned LongMemEval-S dataset that pins the exact source and records a verified SHA256 so future runs are reproducible.

## Required Changes

- Add `benchmarks/download_datasets.py`.
- Pin the cleaned LongMemEval-S source URL from the official dataset.
- Download into `benchmarks/datasets/longmemeval/`.
- Record the verified SHA256 in a committed lock location that later tasks can read without re-downloading.
- Write a local manifest next to the downloaded file with URL, size, SHA256, and retrieval timestamp.
- Ensure reruns skip download unless the operator requests a refresh.

## Constraints

- Use the cleaned dataset, not the deprecated original dataset.
- Fail loudly on checksum mismatches.
- Keep downloaded data gitignored.
- Do not leave the expected checksum as `None` or as a TODO.

## Verification

- `uv run python benchmarks/download_datasets.py`
- `uv run python -c "import json, pathlib; p = pathlib.Path('benchmarks/datasets/longmemeval/manifest.json'); print(json.loads(p.read_text())['sha256'])"`
- `uv run python -c "import json, pathlib; p = pathlib.Path('benchmarks/datasets/longmemeval/longmemeval_s_cleaned.json'); data = json.loads(p.read_text()); print(len(data))"`
- `uv run ruff check benchmarks/download_datasets.py`

## Completion Rule

Mark this task complete only when the dataset is downloaded successfully, the committed lock value matches the actual file, and the file is not tracked by git.
