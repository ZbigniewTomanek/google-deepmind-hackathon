#!/bin/bash
# Run all test agent examples sequentially
# Usage: bash test_agents/examples/run_all_tests.sh

API_URL="${API_URL:-http://localhost:8003}"
set -e

echo "========================================="
echo " NeoCortex Test Agents - Full Test Suite"
echo "========================================="
echo

# 1. Health check
echo "--- [1/6] Health check ---"
curl -sf "${API_URL}/health" | python3 -m json.tool
echo

# 2. List agents
echo "--- [2/6] List agents ---"
curl -sf "${API_URL}/agents" | python3 -m json.tool
echo

# 3. Joke
echo "--- [3/6] Joke (sync) ---"
curl -sf -X POST "${API_URL}/agents/chat/run" \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Tell me a joke about programming"}' | python3 -m json.tool
echo

# 4. Search
echo "--- [4/6] Search (sync) ---"
curl -sf -X POST "${API_URL}/agents/chat/run" \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Search YouTube for Python tutorials"}' | python3 -m json.tool
echo

# 5. Task
echo "--- [5/6] Task (sync) ---"
curl -sf -X POST "${API_URL}/agents/chat/run" \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Add a task: review hackathon demo"}' | python3 -m json.tool
echo

# 6. Async mode
echo "--- [6/6] Async mode (fire and poll) ---"
RESPONSE=$(curl -sf -X POST "${API_URL}/agents/chat/run" \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Say hello async", "async_mode": true}')
echo "Immediate response:"
echo "$RESPONSE" | python3 -m json.tool

SESSION_ID=$(echo "$RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['session_id'])")
echo
echo "Polling session ${SESSION_ID}..."
sleep 5
for i in 1 2 3 4 5 6; do
  STATUS=$(curl -sf "${API_URL}/sessions/${SESSION_ID}" | python3 -c "import sys,json; print(json.load(sys.stdin)['status'])")
  echo "  Poll $i: status=$STATUS"
  if [ "$STATUS" = "completed" ] || [ "$STATUS" = "failed" ]; then
    curl -sf "${API_URL}/sessions/${SESSION_ID}" | python3 -m json.tool
    break
  fi
  sleep 5
done

echo
echo "========================================="
echo " All tests complete!"
echo "========================================="
