#!/usr/bin/env bash
# Run all stages sequentially: copy data → call agent API → clear input.
# Requires NeoCortex services and agent API to be running.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

WORKSPACE="$PROJECT_DIR/agent_workspace/.agent_workspace"
INPUT="$WORKSPACE/input"
mkdir -p "$INPUT"

# Setup shared graph (idempotent)
echo "=== Setting up shared graph ==="
bash "$SCRIPT_DIR/setup_shared_graph.sh"

for stage_dir in $(ls -d "$WORKSPACE"/stage* 2>/dev/null | sort -V); do
  stage_name=$(basename "$stage_dir")
  echo "=== Processing $stage_name ==="

  # Copy data files to input (exclude scripts)
  find "$stage_dir" -type f ! -name "*.sh" -exec cp {} "$INPUT/" \;

  # Run the stage script — abort pipeline if it fails
  if ! bash "$stage_dir/${stage_name/stage/stage_}_api_calls.sh"; then
    echo "ERROR: $stage_name failed. Input files preserved in $INPUT for debugging."
    exit 1
  fi

  # Clear input only after successful completion
  rm -f "$INPUT"/*

  echo "=== $stage_name complete ==="
done

echo "=== All stages complete ==="
