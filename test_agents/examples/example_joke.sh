#!/bin/bash
# Example: Ask the chat agent to tell a joke
#
# The chat agent detects the "joke" intent and routes to the joke-subagent,
# which uses the joke-tool to generate a joke and returns it.

API_URL="${API_URL:-http://localhost:8003}"

echo "=== Requesting a joke from the chat agent ==="
echo

curl -s -X POST "${API_URL}/agents/chat/run" \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "Tell me a funny joke about programming and AI agents"
  }' | python3 -m json.tool

echo
echo "=== Done ==="
