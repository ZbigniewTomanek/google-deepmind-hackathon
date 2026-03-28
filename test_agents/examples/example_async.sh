#!/bin/bash
# Example: Run agent in async mode (fire-and-forget, poll for result)
#
# With async_mode=true, the API returns immediately with status="running"
# and you poll GET /sessions/{session_id} until it completes.

API_URL="${API_URL:-http://localhost:8003}"

echo "=== Launching agent in async mode ==="
echo

RESPONSE=$(curl -s -X POST "${API_URL}/agents/chat/run" \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "Tell me a joke about memory and databases",
    "async_mode": true
  }')

echo "Immediate response:"
echo "$RESPONSE" | python3 -m json.tool

SESSION_ID=$(echo "$RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['session_id'])")
echo
echo "Session ID: ${SESSION_ID}"
echo "Polling for result..."
echo

for i in $(seq 1 12); do
  sleep 5
  RESULT=$(curl -s "${API_URL}/sessions/${SESSION_ID}")
  STATUS=$(echo "$RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin)['status'])")
  echo "  [$i] status: $STATUS"
  if [ "$STATUS" = "completed" ] || [ "$STATUS" = "failed" ]; then
    echo
    echo "=== Final result ==="
    echo "$RESULT" | python3 -m json.tool
    exit 0
  fi
done

echo "Timed out waiting for agent to complete"
exit 1
