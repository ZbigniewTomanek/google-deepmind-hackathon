#!/bin/bash
# Example: Inject prepopulated conversation history into agent prompt
#
# The context field passes prior conversation turns to the agent.
# The chat agent sees these inside <CONVERSATION_HISTORY> tags and uses
# them to understand the current request in context.
#
# This simulates an external system (e.g., NeoCortex) passing recalled
# memories or prior session history to the agent.

API_URL="${API_URL:-http://localhost:8003}"

echo "=== Running with injected conversation context ==="
echo

curl -s -X POST "${API_URL}/agents/chat/run" \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "What did we talk about earlier? Can you remember my preferences?",
    "context": [
      {
        "role": "user",
        "content": "My name is Alice and I work at DeepMind on memory systems for AI agents."
      },
      {
        "role": "assistant",
        "content": "Nice to meet you Alice! That sounds like fascinating work at DeepMind. How can I help you today?"
      },
      {
        "role": "user",
        "content": "Can you remember that I prefer Python over JavaScript and I like concise responses?"
      },
      {
        "role": "assistant",
        "content": "Got it! I will remember your preference for Python and keep my responses concise."
      }
    ]
  }' | python3 -m json.tool

echo
echo "=== The agent should reference Alice, DeepMind, Python preference ==="
