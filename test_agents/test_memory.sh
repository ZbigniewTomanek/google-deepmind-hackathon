#!/usr/bin/env bash
# Test memory agents via the agent API (port 8003)
# Usage: ./test_memory.sh
#
# Prerequisites:
#   1. NeoCortex MCP server running on localhost:8000
#   2. test_agents docker services running: cd docker && docker compose up -d

set -euo pipefail

API="http://localhost:8003"
AGENT="chat-with-memory"
BLUE='\033[0;34m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

call() {
    local step="$1" prompt="$2" session="${3:-}"
    echo -e "\n${BLUE}━━━ Step $step ━━━${NC}"
    echo -e "${YELLOW}Prompt:${NC} $prompt"

    local body
    if [ -n "$session" ]; then
        body=$(jq -n --arg p "$prompt" --arg s "$session" '{prompt: $p, session_id: $s}')
    else
        body=$(jq -n --arg p "$prompt" '{prompt: $p}')
    fi

    local resp
    resp=$(curl -s -X POST "$API/agents/$AGENT/run" \
        -H "Content-Type: application/json" \
        -d "$body")

    local status output session_id error
    status=$(echo "$resp" | jq -r '.status')
    output=$(echo "$resp" | jq -r '.output')
    session_id=$(echo "$resp" | jq -r '.session_id')
    error=$(echo "$resp" | jq -r '.error // empty')

    echo -e "${GREEN}Status:${NC} $status"
    if [ -n "$error" ]; then
        echo -e "Error: $error"
    fi
    echo -e "${GREEN}Output:${NC}"
    echo "$output"
    echo "$session_id"
}

echo -e "${BLUE}╔══════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║   NeoCortex Memory Agent Test Suite      ║${NC}"
echo -e "${BLUE}╚══════════════════════════════════════════╝${NC}"

# Healthcheck
echo -e "\n${YELLOW}Checking API health...${NC}"
curl -sf "$API/health" | jq . || { echo "API not reachable at $API"; exit 1; }

# 1. Store a fact
SESSION=$(call "1/5 — Store a fact" \
    "My favorite color is blue. Please remember that." \
    | tail -1)
echo -e "${YELLOW}Session: $SESSION${NC}"

sleep 2

# 2. Recall the fact
call "2/5 — Recall the fact" \
    "What is my favorite color?" \
    "$SESSION"

sleep 2

# 3. Store another fact
call "3/5 — Store another fact" \
    "I also love hiking in the mountains. Remember that too." \
    "$SESSION"

sleep 2

# 4. Recall multiple facts
call "4/5 — Recall multiple facts" \
    "What do you know about me?" \
    "$SESSION"

sleep 2

# 5. Test joke subagent (exercises memory isolation)
call "5/5 — Joke subagent (memory isolation)" \
    "Tell me a joke about programming" \
    "$SESSION"

echo -e "\n${GREEN}━━━ All tests sent ━━━${NC}"
echo -e "Session ID: $SESSION"
echo -e "You can also test in the web UI: http://localhost:4098"
