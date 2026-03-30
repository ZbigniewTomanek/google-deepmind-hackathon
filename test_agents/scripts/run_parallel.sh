#!/usr/bin/env bash
# Copy all media to input/ and run modality processors concurrently.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

WORKSPACE="$PROJECT_DIR/agent_workspace/.agent_workspace"
INPUT="$WORKSPACE/input"
API_URL="${API_URL:-http://localhost:8003}"

mkdir -p "$INPUT"

# Setup shared graph (idempotent)
echo "=== Setting up shared graph ==="
bash "$SCRIPT_DIR/setup_shared_graph.sh"

# Copy ALL media from all stages into input/
echo "=== Copying all media to input/ ==="
for stage_dir in "$WORKSPACE"/stage*/; do
  find "$stage_dir" -type f ! -name "*.sh" -exec cp {} "$INPUT/" \;
done
echo "Files in input/:"
ls -lh "$INPUT/"

# Launch all three processors in parallel
echo ""
echo "=== Launching processors concurrently ==="

run_agent() {
  local name="$1"
  local prompt="$2"
  echo "[START] $name"
  if curl -sf --max-time 900 -X POST "$API_URL/agents/$name/run" \
    -H "Content-Type: application/json" \
    -d "{\"prompt\": \"$prompt\"}" > /tmp/"$name".out 2>&1; then
    echo "[DONE]  $name ✓"
  else
    echo "[FAIL]  $name ✗"
    cat /tmp/"$name".out
    return 1
  fi
}

run_agent "video-processor" \
  "Process all video files in /app/input. Transcribe them, extract key screenshots, and store all findings in the shared research graph (target_graph=ncx_shared__research)." &
PID_VIDEO=$!

run_agent "audio-processor" \
  "Process all audio files in /app/input. Transcribe them and store all findings in the shared research graph (target_graph=ncx_shared__research)." &
PID_AUDIO=$!

run_agent "rss-processor" \
  "Process all RSS/XML feed files in /app/input. Parse them and store all findings in the shared research graph (target_graph=ncx_shared__research)." &
PID_RSS=$!

echo "Waiting for all processors (PIDs: $PID_VIDEO $PID_AUDIO $PID_RSS)..."

FAILED=0
wait $PID_VIDEO || FAILED=$((FAILED + 1))
wait $PID_AUDIO || FAILED=$((FAILED + 1))
wait $PID_RSS   || FAILED=$((FAILED + 1))

echo ""
if [ $FAILED -eq 0 ]; then
  echo "=== All processors complete ==="
  rm -f "$INPUT"/*
else
  echo "=== $FAILED processor(s) failed. Input files preserved for debugging. ==="
  exit 1
fi
