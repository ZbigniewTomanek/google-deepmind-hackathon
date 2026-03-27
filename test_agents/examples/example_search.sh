#!/bin/bash
# Example: Ask the chat agent to search for something
#
# The chat agent detects the "search" intent and routes to the search-orchestrator,
# which evaluates whether to use YouTube or Google search, delegates to the
# appropriate subagent, and returns aggregated results.

API_URL="${API_URL:-http://localhost:8003}"

echo "=== Searching YouTube for Python tutorials ==="
echo

curl -s -X POST "${API_URL}/agents/chat/run" \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "Search YouTube for the latest Python 3.13 features and tutorials"
  }' | python3 -m json.tool

echo
echo "=== Searching the web for MCP documentation ==="
echo

curl -s -X POST "${API_URL}/agents/chat/run" \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "Find me documentation about the Model Context Protocol"
  }' | python3 -m json.tool

echo
echo "=== Done ==="
