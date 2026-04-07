#!/usr/bin/env bash
# Run the taxonomy steward domain health report.
#
# Usage:
#   ./scripts/taxonomy_steward.sh                    # Print to stdout
#   ./scripts/taxonomy_steward.sh --output report.md # Write to file

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"
exec uv run python -m neocortex.domains.steward "$@"
