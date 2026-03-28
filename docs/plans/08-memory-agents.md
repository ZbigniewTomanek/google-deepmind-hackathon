# Plan 08 — Memory Test Agents

> **Date:** 2026-03-28
> **Status:** DRAFT
> **Branch:** `agent_integration_with_mcp`

## Context

The test_agents framework has a `chat` primary agent that routes to subagents (search, task, joke) but doesn't actively test NeoCortex memory. We need two new agents — `chat_with_memory` (primary) and `joke_with_memory` (subagent) — that exercise `remember`, `recall`, and `discover` MCP tools with **per-agent memory isolation**. Each agent authenticates to the same NeoCortex MCP server with a different bearer token, giving it a separate `agent_id` and its own PostgreSQL schema (`ncx_{agent_id}__personal`).

### Why per-agent MCP isolation matters

Without isolation, all agents write to the same memory graph. With isolation, `chat_with_memory` memories are invisible to `joke_with_memory` and vice versa — proving that NeoCortex's multi-tenant architecture works end-to-end through the full agent stack.

## Architecture

```
chat_with_memory (primary, temp=0.4)
├── joke_with_memory (subagent, temp=0.7)
│   └── joke-tool (ScriptTool)            ← existing
│   └── MCP: neocortex-joke               ← agent_id = "joke-agent"
└── MCP: neocortex-chat                    ← agent_id = "chat-agent"

opencode.json (global MCP config):
  neocortex-chat  → npx mcp-remote <url> --header Authorization:Bearer chat-agent-token
  neocortex-joke  → npx mcp-remote <url> --header Authorization:Bearer joke-agent-token

Permission enforcement (AgentPermissions.extra → permission: section):
  chat_with_memory:  "neocortex-chat*": allow   (everything else blocked by "*": deny)
  joke_with_memory:  "neocortex-joke*": allow   (everything else blocked by "*": deny)
```

### Key mechanisms (all already exist)

| Mechanism | Where | How |
|-----------|-------|-----|
| Multiple MCP servers | `ConfigBuilder.mcp_server()` | Call multiple times with different names |
| Auth header passing | `mcp-remote --header` | `npx mcp-remote <url> --header "Authorization:Bearer <token>"` |
| Token → agent_id mapping | `dev_tokens.json` | `{"chat-agent-token": "chat-agent", ...}` |
| Per-agent MCP restriction | `AgentPermissions.extra` | Glob patterns: `("neocortex-chat*", "allow")` — inserted before the compiler's global `"*": deny` in the `permission:` section, so specific allows take precedence |
| Schema isolation | NeoCortex `GraphRouter` | Routes to `ncx_{agent_id}__personal` |

**No OpenAgentCompiler changes required.** All features are already implemented.

## Critical Files

### Files to modify

| File | Change |
|------|--------|
| `dev_tokens.json` | Add `chat-agent-token` and `joke-agent-token` entries |
| `test_agents/.env` | Add `NEOCORTEX_CHAT_TOKEN` and `NEOCORTEX_JOKE_TOKEN` env vars |
| `test_agents/.env.example` | Mirror new env vars |
| `test_agents/agents/config.py` | Register two named MCP servers with auth headers |
| `test_agents/agents/__init__.py` | Export new builder functions |
| `test_agents/build_agents.py` | Add new agents to compilation list |

### Files to create

| File | Purpose |
|------|---------|
| `test_agents/agents/chat_with_memory.py` | Primary agent: memory-first conversation |
| `test_agents/agents/joke_with_memory.py` | Subagent: remembers joke preferences |

### Reference files (read-only)

| File | Why |
|------|-----|
| `test_agents/agents/chat.py` | Pattern for primary agent with subagents + workflow |
| `test_agents/agents/joke.py` | Pattern for subagent with tool + workflow |
| `.venv/.../open_agent_compiler/compiler.py:1298-1350` | How `"*": deny` + `AgentPermissions.extra` allows are emitted into the `permission:` section |
| `.venv/.../open_agent_compiler/compiler.py:865-871` | `_merge_tool_permissions` — MCP tuple patterns become top-level entries |
| `src/neocortex/auth/dev.py` | `DevTokenAuth.verify_token()` — maps tokens to agent_ids |
| `src/neocortex/auth/tokens.py` | `load_token_map()` — reads `dev_tokens.json` |

## Stages

---

### Stage 1: Token & environment setup

Add agent tokens and environment variables for per-agent MCP auth.

**Steps:**

1. Edit `dev_tokens.json` — add two new entries:
   ```json
   {
     "alice-token": "alice",
     "bob-token": "bob",
     "shared-token": "shared",
     "dev-token-neocortex": "dev-user",
     "chat-agent-token": "chat-agent",
     "joke-agent-token": "joke-agent"
   }
   ```

2. Edit `test_agents/.env` — add token env vars (keep the existing `NEOCORTEX_AUTH_TOKEN` which is used by the unauthenticated `neocortex` MCP server for non-memory agents):
   ```
   NEOCORTEX_CHAT_TOKEN=chat-agent-token
   NEOCORTEX_JOKE_TOKEN=joke-agent-token
   ```

3. Edit `test_agents/.env.example` — mirror the new vars with placeholder values.

**Verification:**
- `cat dev_tokens.json | python -m json.tool` — valid JSON with 6 entries
- `grep NEOCORTEX_.*TOKEN test_agents/.env` — both vars present

**Commit:** `feat(test-agents): add per-agent MCP auth tokens`

---

### Stage 2: Dual MCP server configuration

Update `config.py` to register two named MCP servers with different auth headers.

**Steps:**

1. Edit `test_agents/agents/config.py`:
   - Read `NEOCORTEX_CHAT_TOKEN` and `NEOCORTEX_JOKE_TOKEN` from env
   - Replace the single `.mcp_server("neocortex", ...)` with two calls:
     ```python
     mcp_url = os.environ.get("NEOCORTEX_MCP_URL", "http://localhost:8000")
     chat_token = os.environ.get("NEOCORTEX_CHAT_TOKEN", "chat-agent-token")
     joke_token = os.environ.get("NEOCORTEX_JOKE_TOKEN", "joke-agent-token")

     return (
         ConfigBuilder()
         .provider(...)
         .default_model(...)
         # Original single MCP for existing agents (no auth)
         .mcp_server(name="neocortex", command="npx", args=["mcp-remote", mcp_url])
         # Per-agent MCP with auth tokens
         .mcp_server(
             name="neocortex-chat",
             command="npx",
             args=["mcp-remote", mcp_url, "--header", f"Authorization:Bearer {chat_token}"],
         )
         .mcp_server(
             name="neocortex-joke",
             command="npx",
             args=["mcp-remote", mcp_url, "--header", f"Authorization:Bearer {joke_token}"],
         )
         .compaction(auto=True, prune=True)
         .build()
     )
     ```

   **Note:** Keep the original `neocortex` MCP server so existing agents (chat, search, task, joke) are unaffected.

**Verification:**
- `cd test_agents && uv run python -c "from agents.config import build_config; c = build_config(); print(len(c.mcp_servers))"` — prints `3`

**Commit:** `feat(test-agents): register per-agent MCP servers with auth headers`

---

### Stage 3: `chat_with_memory` primary agent

Create the memory-first primary chat agent.

**Steps:**

1. Create `test_agents/agents/chat_with_memory.py`:

   **Agent design:**
   - Mode: `primary`
   - Temperature: 0.4
   - MCP: `neocortex-chat` only (via permissions)
   - Subagent: `joke_with_memory`
   - Steps: 100

   **Workflow (4 steps):**

   | Step | Name | Logic |
   |------|------|-------|
   | 1 | Recall Context | Always run `neocortex-chat` `recall` with the user's message to check for prior memories. Run `discover` to understand available knowledge. |
   | 2 | Analyze Intent | Evaluate intent: `joke`, `remember`, `general`. Route accordingly. |
   | 3 | Joke | Gate on `intent=joke`. Invoke `joke_with_memory` subagent. |
   | 4 | Respond & Remember | Gate on `intent=remember` or `intent=general`. Answer the user. Use `neocortex-chat` `remember` to store important facts from the conversation. |

   **Permissions:**
   ```python
   .permissions(AgentPermissions(
       extra=(("neocortex-chat*", "allow"),),
   ))
   ```
   `extra` entries are emitted first in the `permission:` section by `_agent_permissions_to_dict`,
   so `"neocortex-chat*": allow` precedes the compiler's global `"*": deny` (line 1305).
   This lets MCP tools from `neocortex-chat` through while blocking `neocortex-joke` tools.

   **Preamble focus:** Emphasize that this agent should actively use memory:
   - Always recall before responding to check for relevant context
   - Store important facts, user preferences, and conversation highlights
   - Reference recalled memories naturally in responses
   - Use `discover` to understand what's in the knowledge graph

2. Register subagent reference:
   ```python
   joke_mem_ref = SubagentBuilder().name("joke-with-memory").description("Tells jokes, remembers preferences").build()
   ```

**Verification:**
- `uv run python -c "from agents.chat_with_memory import build_chat_with_memory; from agents.config import build_config; a = build_chat_with_memory(build_config()); print(a.name, a.mode)"` — prints `chat-with-memory primary`

**Commit:** `feat(test-agents): add chat_with_memory primary agent`

---

### Stage 4: `joke_with_memory` subagent

Create the memory-enabled joke subagent.

**Steps:**

1. Create `test_agents/agents/joke_with_memory.py`:

   **Agent design:**
   - Mode: `subagent`
   - Temperature: 0.7
   - MCP: `neocortex-joke` only (via permissions)
   - Tool: `joke-tool` (existing)

   **Workflow (3 steps):**

   | Step | Name | Logic |
   |------|------|-------|
   | 1 | Recall Preferences | Run `neocortex-joke` `recall` to check for user's joke preferences (favorite topics, preferred style). |
   | 2 | Generate Joke | Use `joke-tool` with the topic. If preferences were recalled, apply them. |
   | 3 | Remember Feedback | Use `neocortex-joke` `remember` to store the joke topic and style for future personalization. |

   **Permissions:**
   ```python
   .permissions(AgentPermissions(
       extra=(("neocortex-joke*", "allow"),),
   ))
   ```
   Same mechanism as `chat_with_memory` — `extra` entries precede `"*": deny`,
   allowing only `neocortex-joke` MCP tools.

   **Preamble focus:** Remember joke preferences across conversations — topics the user likes, preferred joke styles. Use recalled preferences to personalize jokes.

**Verification:**
- `uv run python -c "from agents.joke_with_memory import build_joke_with_memory; from agents.config import build_config; a = build_joke_with_memory(build_config()); print(a.name, a.mode)"` — prints `joke-with-memory subagent`

**Commit:** `feat(test-agents): add joke_with_memory subagent`

---

### Stage 5: Build pipeline registration

Wire both agents into the build pipeline.

**Steps:**

1. Edit `test_agents/agents/__init__.py` — add exports:
   ```python
   from agents.chat_with_memory import build_chat_with_memory
   from agents.joke_with_memory import build_joke_with_memory
   ```

2. Edit `test_agents/build_agents.py`:
   - Add imports for the new builders
   - Add both agents to the `agents` list:
     ```python
     agents = [
         build_chat(config),
         build_search_orchestrator(config),
         build_task_subagent(config),
         build_joke_subagent(config),
         build_chat_with_memory(config),    # New
         build_joke_with_memory(config),     # New
     ]
     ```

**Verification:**
- `cd test_agents && uv run python build_agents.py` — compiles without errors, lists 6 agents
- `ls build/.opencode/agents/` — includes `chat-with-memory.md` and `joke-with-memory.md`
- `cat build/opencode.json | python -m json.tool | grep neocortex` — shows all 3 MCP entries

**Commit:** `feat(test-agents): register memory agents in build pipeline`

---

### Stage 6: Validate compiled output

Verify the compiled agents have correct MCP permissions.

**Steps:**

1. Inspect `build/.opencode/agents/chat-with-memory.md`:
   - Frontmatter should have `"neocortex-chat*": allow` in permission section
   - Should NOT have `neocortex-joke*` allow
   - Should reference `joke-with-memory` as subagent

2. Inspect `build/.opencode/agents/joke-with-memory.md`:
   - Frontmatter should have `"neocortex-joke*": allow` in permission section
   - Should NOT have `neocortex-chat*` allow

3. Inspect `build/opencode.json`:
   - `mcp` section should have 3 entries: `neocortex`, `neocortex-chat`, `neocortex-joke`
   - Chat/joke entries should include `--header` args with correct tokens

4. Verify existing agents unchanged:
   - `build/.opencode/agents/chat.md` should be identical to before
   - Other agents unaffected

5. Verify MCP tool naming matches permission globs:
   - Start the NeoCortex MCP server, connect via `npx mcp-remote`, and list available tools
   - Confirm tool names are prefixed with the MCP server name (e.g., `neocortex-chat__remember`)
   - Verify the glob `neocortex-chat*` matches all tools from that server and no tools from `neocortex-joke`

**Verification:**
- `grep -A2 'neocortex-chat' build/.opencode/agents/chat-with-memory.md` — shows allow
- `grep -A2 'neocortex-joke' build/.opencode/agents/joke-with-memory.md` — shows allow
- `grep 'neocortex-chat' build/.opencode/agents/joke-with-memory.md` — empty (no cross-allow)
- `grep 'neocortex-joke' build/.opencode/agents/chat-with-memory.md` — empty (no cross-allow)
- Existing agents compile identically

**Commit:** No commit — validation only.

---

## E2E Testing Guide

### Prerequisites
```bash
# Start NeoCortex with dev_token auth
NEOCORTEX_AUTH_MODE=dev_token \
NEOCORTEX_DEV_TOKENS_FILE=dev_tokens.json \
docker compose up -d postgres
uv run python -m neocortex
```

### Manual test flow
```bash
# 1. Start services
cd test_agents/docker && docker compose up -d

# 2. Test chat_with_memory stores a fact
curl -X POST http://localhost:8003/agents/chat-with-memory/run \
  -H "Content-Type: application/json" \
  -d '{"prompt": "My favorite color is blue. Please remember that."}'

# 3. Test chat_with_memory recalls the fact
curl -X POST http://localhost:8003/agents/chat-with-memory/run \
  -H "Content-Type: application/json" \
  -d '{"prompt": "What is my favorite color?"}'

# 4. Test joke_with_memory can't see chat memories (isolation)
curl -X POST http://localhost:8003/agents/chat-with-memory/run \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Tell me a joke about programming"}'
# joke_with_memory runs as subagent, stores to its own schema

# 5. Verify DB isolation
psql -h localhost -U neocortex -d neocortex -c \
  "SELECT schema_name FROM information_schema.schemata WHERE schema_name LIKE 'ncx_%';"
# Should show: ncx_chat_agent__personal, ncx_joke_agent__personal
```

---

## Progress Tracker

| Stage | Status | Notes |
|-------|--------|-------|
| 1. Token & env setup | DONE | Added chat-agent-token and joke-agent-token to dev_tokens.json; added NEOCORTEX_CHAT_TOKEN and NEOCORTEX_JOKE_TOKEN to .env and .env.example |
| 2. Dual MCP config | DONE | Added neocortex-chat and neocortex-joke MCP servers with auth headers; kept original neocortex server for existing agents |
| 3. chat_with_memory agent | DONE | Created chat_with_memory.py with 4-step workflow (recall, analyze, joke routing, respond+remember); permissions restrict to neocortex-chat MCP only |
| 4. joke_with_memory subagent | DONE | Created joke_with_memory.py with 3-step workflow (recall preferences, generate joke, remember feedback); permissions restrict to neocortex-joke MCP only |
| 5. Build pipeline registration | DONE | Added exports to __init__.py; added both builders to build_agents.py; compiles 6 agents successfully |
| 6. Validate compiled output | TODO | |

Last stage completed: Stage 5 — Build pipeline registration
Last updated by: plan-runner-agent
