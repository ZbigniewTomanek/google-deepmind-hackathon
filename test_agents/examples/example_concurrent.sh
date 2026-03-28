#!/bin/bash
# Fire multiple agent requests concurrently in async mode, then poll all
API_URL="${API_URL:-http://localhost:8003}"

echo "=== Firing 3 concurrent agent requests ==="
echo

# Launch all 3 in parallel
S1=$(curl -s -X POST "${API_URL}/agents/chat/run" -H "Content-Type: application/json" \
  -d '{"prompt": "Tell me a joke about databases", "async_mode": true}')
S2=$(curl -s -X POST "${API_URL}/agents/chat/run" -H "Content-Type: application/json" \
  -d '{"prompt": "Search YouTube for MCP protocol tutorials", "async_mode": true}')
S3=$(curl -s -X POST "${API_URL}/agents/chat/run" -H "Content-Type: application/json" \
  -d '{"prompt": "Add a task: deploy demo to production", "async_mode": true}')

ID1=$(echo "$S1" | python3 -c "import sys,json; print(json.load(sys.stdin)['session_id'])")
ID2=$(echo "$S2" | python3 -c "import sys,json; print(json.load(sys.stdin)['session_id'])")
ID3=$(echo "$S3" | python3 -c "import sys,json; print(json.load(sys.stdin)['session_id'])")

echo "  [joke]   session: $ID1"
echo "  [search] session: $ID2"
echo "  [task]   session: $ID3"
echo
echo "All 3 running concurrently. Polling..."
echo

for i in $(seq 1 36); do
  sleep 5
  R1=$(curl -s "${API_URL}/sessions/${ID1}" | python3 -c "import sys,json; print(json.load(sys.stdin)['status'])")
  R2=$(curl -s "${API_URL}/sessions/${ID2}" | python3 -c "import sys,json; print(json.load(sys.stdin)['status'])")
  R3=$(curl -s "${API_URL}/sessions/${ID3}" | python3 -c "import sys,json; print(json.load(sys.stdin)['status'])")
  echo "  [$i] joke=$R1  search=$R2  task=$R3"

  if [ "$R1" != "running" ] && [ "$R2" != "running" ] && [ "$R3" != "running" ]; then
    echo
    echo "=== All done! Results ==="
    echo
    echo "--- Joke ---"
    curl -s "${API_URL}/sessions/${ID1}" | python3 -m json.tool
    echo
    echo "--- Search ---"
    curl -s "${API_URL}/sessions/${ID2}" | python3 -m json.tool
    echo
    echo "--- Task ---"
    curl -s "${API_URL}/sessions/${ID3}" | python3 -m json.tool
    exit 0
  fi
done

echo "Timed out"
exit 1
