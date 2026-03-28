# Plan: Research Agent Decomposition into Modality Subagents

## Overview

Decompose the monolithic `research-agent` into a primary orchestrator with modality-specific subagents (video, audio, RSS). Add a Docker-mounted `/app/input` directory, a file-listing tool, local-file processing tools, shared memory via ingestion API, a `chat-with-extractions` agent for querying shared knowledge, and a stage runner script that feeds pre-downloaded data through the pipeline.

## Architecture

```
research-orchestrator (primary, temp=0.3)
├── list-input-files (ScriptTool) — lists /app/input with file types
├── video-processor (subagent, temp=0.3)
│   ├── transcribe-local-video (ScriptTool)
│   ├── video-screenshot (existing ScriptTool)
│   └── MCP: neocortex-video-proc (token → shared graph via target_graph)
├── audio-processor (subagent, temp=0.3)
│   ├── transcribe-local-audio (ScriptTool)
│   └── MCP: neocortex-audio-proc (token → shared graph via target_graph)
├── rss-processor (subagent, temp=0.3)
│   ├── parse-local-rss (ScriptTool)
│   └── MCP: neocortex-rss-proc (token → shared graph via target_graph)
└── MCP: neocortex-research-orch (token → shared read)

chat-with-extractions (primary, temp=0.4)
└── MCP: neocortex-chat-extractions (token → shared read)

Shared graph: ncx_shared__research
  - video-processor, audio-processor, rss-processor: read+write
  - research-orchestrator, chat-extractions: read+write

Note: Subagents write to the shared graph via MCP remember(target_graph=...)
rather than a separate HTTP ScriptTool. No personal graphs for ephemeral
subagents — all findings go directly to the shared graph.
```

### Data Flow

```
Stage Runner (bash, set -e)
  │
  ├─ setup_shared_graph.sh (idempotent — create graph + grant permissions)
  │
  ├─ cp stage1/*.mp4 → input/
  ├─ POST /agents/research-orchestrator/run  (blocks until done)
  │   └─ Orchestrator:
  │       1. list-input-files → sees .mp4
  │       2. delegates to video-processor subagent
  │       3. video-processor: transcribe → remember(target_graph=shared) via MCP
  │       4. orchestrator summarizes
  ├─ (only rm input/* after API returns 200)
  │
  ├─ cp stage2/*.mp3 → input/
  ├─ POST /agents/research-orchestrator/run
  │   └─ audio-processor: transcribe → remember(target_graph=shared) via MCP
  ├─ rm input/*
  │
  ├─ cp stage3/*.rss → input/
  ├─ POST /agents/research-orchestrator/run
  │   └─ rss-processor: parse → remember(target_graph=shared) via MCP
  └─ rm input/*

Then:
  POST /agents/chat-with-extractions/run
    └─ recall from shared graph → answer questions about all ingested data
```

## Execution Protocol

Execute stages sequentially. Each stage ends with a commit. If verification fails, stop and investigate before proceeding.

---

## Stage 1: New ScriptTool Implementations

Create 3 new tool scripts in `test_agents/agent_scripts/`.

### Steps

1. **Create `list_input_files.py`** — ScriptTool that lists files in a directory (default `/app/input`) with file extensions and sizes.
   - Input: `directory` (str, default="/app/input")
   - Output: `files` (list of {name, path, extension, size_bytes}), `total_count` (int)

2. **Create `transcribe_local_video.py`** — Like `transcribe_video.py` but takes a local file path instead of YouTube URL. Skips yt-dlp download, goes straight to Gemini upload.
   - Input: `video_path` (str), `output_dir` (str, default=".agent_workspace")
   - Output: `transcript` (list[dict]), `full_text` (str), `video_path` (str), `duration_seconds` (float), `title` (str)

3. **Create `transcribe_local_audio.py`** — Like `transcribe_audio.py` but takes a local file path. Skips yt-dlp download.
   - Input: `audio_path` (str), `output_dir` (str, default=".agent_workspace")
   - Output: `transcript` (list[dict]), `full_text` (str), `audio_path` (str), `duration_seconds` (float), `title` (str)

4. **Create `parse_local_rss.py`** — Like `hackernews_rss.py` but reads from a local file path instead of URL.
   - Input: `file_path` (str), `max_items` (int, default=10)
   - Output: `items` (list[dict]), `feed_title` (str), `total_fetched` (int)

Note: No `store_shared.py` needed — subagents write to the shared graph via
MCP `remember(target_graph="ncx_shared__research")`, which is already built
into the NeoCortex MCP server (`src/neocortex/tools/remember.py`).

### Verification

```bash
cd test_agents
uv run python agent_scripts/list_input_files.py --directory /tmp --json
uv run python agent_scripts/parse_local_rss.py --help
```

### Commit

`feat(agents): add local-file processing ScriptTools`

---

## Stage 2: Tool Builder Functions

Register all new tools in `test_agents/agents/tools.py`.

### Steps

1. Add `build_list_input_files()` — ToolBuilder for `list_input_files.py`
2. Add `build_transcribe_local_video()` — ToolBuilder for `transcribe_local_video.py`
3. Add `build_transcribe_local_audio()` — ToolBuilder for `transcribe_local_audio.py`
4. Add `build_parse_local_rss()` — ToolBuilder for `parse_local_rss.py`

### Verification

```bash
cd test_agents && uv run python -c "from agents.tools import build_list_input_files, build_parse_local_rss; print('OK')"
```

### Commit

`feat(agents): register new tool builders for local processing`

---

## Stage 3: Config — New Tokens, MCP Servers, and Shared Graph Setup

### Steps

1. **Update `dev_tokens.json`** — Add tokens for new agents:
   ```json
   "research-orch-token": "research-orch",
   "video-processor-token": "video-processor",
   "audio-processor-token": "audio-processor",
   "rss-processor-token": "rss-processor",
   "chat-extractions-token": "chat-extractions"
   ```

2. **Update `test_agents/agents/config.py`** — Add environment variable reads and MCP server registrations for each new agent. Use direct URL + headers transport (like neocortex-chat), NOT mcp-remote stdio proxy:
   ```python
   # Example — same pattern for all 5 new servers:
   .mcp_server(
       name="neocortex-video-proc",
       url=mcp_url,
       headers={"Authorization": f"Bearer {video_proc_token}"},
   )
   ```
   Servers to add: `neocortex-research-orch`, `neocortex-video-proc`, `neocortex-audio-proc`, `neocortex-rss-proc`, `neocortex-chat-extractions`.

   Also remove or replace the existing `neocortex-research` mcp-remote entry — the new `neocortex-research-orch` replaces it with the simpler URL+headers transport.

3. **Update `test_agents/.env.example`** and `test_agents/.env` — Add new token env vars with defaults.

4. **Create `test_agents/scripts/setup_shared_graph.sh`** — Sets up the shared graph and permissions (idempotent). Must run after NeoCortex services are up:
   ```bash
   ADMIN_TOKEN="${NEOCORTEX_ADMIN_TOKEN:-admin-token-neocortex}"
   BASE_URL="${NEOCORTEX_INGESTION_URL:-http://localhost:8001}"

   # Create ncx_shared__research (ignore 409 if exists)
   curl -sf -X POST "$BASE_URL/admin/graphs" \
     -H "Authorization: Bearer $ADMIN_TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"purpose": "research"}' || true

   # Grant read+write to all research agents
   for agent in video-processor audio-processor rss-processor research-orch chat-extractions; do
     curl -sf -X POST "$BASE_URL/admin/permissions" \
       -H "Authorization: Bearer $ADMIN_TOKEN" \
       -H "Content-Type: application/json" \
       -d "{\"agent_id\": \"$agent\", \"schema_name\": \"ncx_shared__research\", \"can_read\": true, \"can_write\": true}"
   done
   ```

### Verification

```bash
cd test_agents && uv run python -c "from agents.config import build_config; c = build_config(); print('OK')"
bash test_agents/scripts/setup_shared_graph.sh  # with services running
```

### Commit

`feat(config): add tokens, MCP servers, and shared graph setup for decomposed research agents`

---

## Stage 4: Subagent Definitions

Create 3 new subagent files in `test_agents/agents/`.

Subagents are ephemeral (no session continuity), so they skip personal graph
storage and write directly to the shared graph via MCP
`remember(target_graph="ncx_shared__research")`.

### Steps

1. **Create `video_processor.py`** — `build_video_processor(config)`:
   - Mode: subagent
   - Tools: transcribe-local-video, video-screenshot
   - MCP: neocortex-video-proc
   - Workflow:
     - Step 1: Process Video — transcribe local video file, extract screenshots at key moments
     - Step 2: Share Findings — store transcript segments and visual findings to shared graph via MCP `remember(target_graph="ncx_shared__research")`
   - Permissions: `extra=(("neocortex-video-proc*", "allow"),)`

2. **Create `audio_processor.py`** — `build_audio_processor(config)`:
   - Mode: subagent
   - Tools: transcribe-local-audio
   - MCP: neocortex-audio-proc
   - Workflow:
     - Step 1: Process Audio — transcribe local audio file
     - Step 2: Share Findings — store transcript and key findings to shared graph via MCP `remember(target_graph="ncx_shared__research")`
   - Permissions: `extra=(("neocortex-audio-proc*", "allow"),)`

3. **Create `rss_processor.py`** — `build_rss_processor(config)`:
   - Mode: subagent
   - Tools: parse-local-rss
   - MCP: neocortex-rss-proc
   - Workflow:
     - Step 1: Process RSS — parse local RSS file
     - Step 2: Share Findings — store parsed items and key findings to shared graph via MCP `remember(target_graph="ncx_shared__research")`
   - Permissions: `extra=(("neocortex-rss-proc*", "allow"),)`

### Verification

```bash
cd test_agents && uv run python -c "
from agents.video_processor import build_video_processor
from agents.audio_processor import build_audio_processor
from agents.rss_processor import build_rss_processor
from agents.config import build_config
config = build_config()
v = build_video_processor(config)
a = build_audio_processor(config)
r = build_rss_processor(config)
print(f'Built: {v.name}, {a.name}, {r.name}')
"
```

### Commit

`feat(agents): add video-processor, audio-processor, rss-processor subagents`

---

## Stage 5: Research Orchestrator (Refactored)

Replace the monolithic `research.py` with a routing orchestrator.

### Steps

1. **Rewrite `test_agents/agents/research.py`** — `build_research_orchestrator(config)`:
   - Name: `research-orchestrator`
   - Mode: primary
   - Tools: list-input-files
   - Subagents: video-processor, audio-processor, rss-processor
   - MCP: neocortex-research-orch
   - Permissions: `extra=(("neocortex-research-orch*", "allow"),)`
   - Workflow:
     - Step 1: Recall Context — check memory for prior knowledge via MCP
     - Step 2: Scan Input — use list-input-files to see what's in /app/input
     - Step 3: Classify & Route — evaluate file types:
       - `.mp4`, `.webm`, `.mkv` → delegate to video-processor
       - `.mp3`, `.wav`, `.opus`, `.m4a` → delegate to audio-processor
       - `.rss`, `.xml`, `.atom` → delegate to rss-processor
       - Gate/route pattern for each modality
     - Step 4: Summarize — collect results and present summary

2. **Update `test_agents/agents/__init__.py`** — Replace `build_research_agent` with new exports.

### Verification

```bash
cd test_agents && uv run python -c "
from agents.research import build_research_orchestrator
from agents.config import build_config
r = build_research_orchestrator(build_config())
print(f'Built: {r.name}, subagents: {[s.name for s in (r.subagents or [])]}')
"
```

### Commit

`refactor(agents): replace monolithic research-agent with research-orchestrator + subagent routing`

---

## Stage 6: Chat With Extractions Agent

### Steps

1. **Create `test_agents/agents/chat_with_extractions.py`** — `build_chat_with_extractions(config)`:
   - Name: `chat-with-extractions`
   - Mode: primary
   - MCP: neocortex-chat-extractions
   - Permissions: `extra=(("neocortex-chat-extractions*", "allow"),)`
   - Workflow:
     - Step 1: Recall — search shared + personal graphs via MCP recall
     - Step 2: Discover — explore knowledge graph structure via MCP discover
     - Step 3: Respond — answer user questions using recalled knowledge
     - Step 4: Remember — store conversation insights in personal memory
   - Preamble explains this agent has access to all research findings via shared graph
   - Color: `#FF6B35`

### Verification

```bash
cd test_agents && uv run python -c "
from agents.chat_with_extractions import build_chat_with_extractions
from agents.config import build_config
a = build_chat_with_extractions(build_config())
print(f'Built: {a.name}')
"
```

### Commit

`feat(agents): add chat-with-extractions agent for querying shared research graph`

---

## Stage 7: Build Pipeline & Docker Updates

### Steps

1. **Update `test_agents/build_agents.py`**:
   - Import new builders: `build_video_processor`, `build_audio_processor`, `build_rss_processor`, `build_research_orchestrator`, `build_chat_with_extractions`
   - Remove old `build_research_agent` import
   - Add all new agents to the `agents` list
   - Add `feedparser` to `_BUILD_PYPROJECT` dependencies

2. **Update `test_agents/docker/docker-compose.yml`**:
   - Add volume mount for input directory:
     ```yaml
     # In agent-api service volumes:
     - ${PROJECT_ROOT}/test_agents/agent_workspace/.agent_workspace/input:/app/input
     ```
   - Also mount in opencode-web for script access.

3. **Update `test_agents/agents/__init__.py`** with all new exports.

### Verification

```bash
cd test_agents && uv run python build_agents.py
ls build/.opencode/agents/
# Should show: research-orchestrator.md, video-processor.md, audio-processor.md,
#              rss-processor.md, chat-with-extractions.md, plus existing agents
```

### Commit

`feat(build): update compilation pipeline and Docker mounts for decomposed research agents`

---

## Stage 8: Stage Runner Script & API Call Scripts

Note: `setup_shared_graph.sh` was already created in Stage 3.

### Steps

1. **Write `stage_1_api_calls.sh`** — Triggers research-orchestrator for video processing:
   ```bash
   curl -sf -X POST http://localhost:8003/agents/research-orchestrator/run \
     -H "Content-Type: application/json" \
     -d '{"prompt": "Process all video files in /app/input. Transcribe them, extract key screenshots, and store findings in the shared research graph."}'
   ```

2. **Write `stage_2_api_calls.sh`** — Triggers research-orchestrator for audio processing.

3. **Write `stage_3_api_calls.sh`** — Triggers research-orchestrator for RSS processing.

4. **Create `test_agents/scripts/run_stages.sh`** — Main stage runner with error handling:
   ```bash
   #!/usr/bin/env bash
   set -euo pipefail

   WORKSPACE=agent_workspace/.agent_workspace
   INPUT=$WORKSPACE/input
   mkdir -p "$INPUT"

   # Setup shared graph (idempotent)
   echo "=== Setting up shared graph ==="
   bash scripts/setup_shared_graph.sh

   for stage_dir in $(ls -d $WORKSPACE/stage* 2>/dev/null | sort -V); do
     stage_name=$(basename "$stage_dir")
     echo "=== Processing $stage_name ==="

     # Copy data files to input (exclude scripts)
     find "$stage_dir" -type f ! -name "*.sh" -exec cp {} "$INPUT/" \;

     # Run the stage script — abort pipeline if it fails
     if ! bash "$stage_dir/${stage_name/stage/stage_}_api_calls.sh"; then
       echo "ERROR: $stage_name failed. Input files preserved in $INPUT for debugging."
       exit 1
     fi

     # Clear input only after successful completion
     rm -f "$INPUT"/*

     echo "=== $stage_name complete ==="
   done

   echo "=== All stages complete ==="
   ```

### Verification

```bash
cat test_agents/agent_workspace/.agent_workspace/stage1/stage_1_api_calls.sh
bash test_agents/scripts/run_stages.sh  # with services running
```

### Commit

`feat(scripts): add stage runner and per-stage API call scripts`

---

## Stage 9: Validation

### Steps

1. Compile all agents: `cd test_agents && uv run python build_agents.py`
2. Verify all agent markdown files exist in `build/.opencode/agents/`
3. Verify all script files copied to `build/scripts/`
4. Verify Docker compose is valid: `cd test_agents/docker && docker compose config`
5. Dry-run the stage runner (with services stopped — just verify file copy logic)

### Commit

No commit — validation only.

---

## Progress Tracker

| Stage | Description | Status | Notes |
|-------|-------------|--------|-------|
| 1 | New ScriptTool implementations (3 scripts) | DONE | Created list_input_files.py, transcribe_local_video.py, transcribe_local_audio.py, parse_local_rss.py; added feedparser dep |
| 2 | Tool builder functions (4 builders) | DONE | Added build_list_input_files, build_transcribe_local_video, build_transcribe_local_audio, build_parse_local_rss to tools.py |
| 3 | Config — tokens, MCP servers, shared graph setup | DONE | Added 5 tokens, 5 MCP servers (URL+headers), env vars, setup_shared_graph.sh |
| 4 | Subagent definitions | DONE | Created video_processor.py, audio_processor.py, rss_processor.py — all write to shared graph via MCP |
| 5 | Research orchestrator (refactored) | DONE | Rewrote research.py as routing orchestrator with list-input-files tool + 3 subagent refs; updated __init__.py exports |
| 6 | Chat-with-extractions agent | DONE | Created chat_with_extractions.py — primary agent with 4-step MCP workflow (recall, discover, respond, remember); updated __init__.py exports |
| 7 | Build pipeline & Docker updates | DONE | Updated build_agents.py imports (removed build_research_agent, added 5 new builders), added feedparser dep, added input volume mounts to docker-compose.yml; __init__.py already updated in prior stages |
| 8 | Stage runner & API call scripts | PENDING | set -e, fail-fast error handling |
| 9 | Validation | PENDING | |

Last stage completed: Stage 7 — Build pipeline & Docker updates
Last updated by: plan-runner-agent
