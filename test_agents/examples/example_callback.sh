#!/bin/bash
# Example: Run an agent with a callback URL
#
# When the agent finishes, the server POSTs the full session result
# (including output, error, and conversation context) to the callback URL.
#
# To test, start a simple listener first:
#   python3 -m http.server 9999
# Then run this script. You'll see the callback POST in the listener's logs.

API_URL="${API_URL:-http://localhost:8003}"
CALLBACK_URL="${CALLBACK_URL:-http://localhost:9999/webhook/session-complete}"

echo "=== Running agent with callback URL ==="
echo "Callback will be sent to: ${CALLBACK_URL}"
echo

curl -s -X POST "${API_URL}/agents/chat/run" \
  -H "Content-Type: application/json" \
  -d "{
    \"prompt\": \"Tell me a joke about AI memory systems\",
    \"callback_url\": \"${CALLBACK_URL}\"
  }" | python3 -m json.tool

echo
echo "=== Initial response received (callback fires asynchronously) ==="
echo "Check your listener for the callback POST with full session context."
