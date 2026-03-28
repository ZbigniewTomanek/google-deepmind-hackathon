#!/usr/bin/env bash
set -euo pipefail
echo "=== Running media ingestion E2E tests ==="
NEOCORTEX_MOCK_DB=true uv run pytest tests/e2e/test_media_e2e.py -v --tb=short
echo ""
echo "=== Running full test suite (regression) ==="
uv run pytest tests/ -v --tb=short
echo ""
echo "All E2E and regression tests passed."
