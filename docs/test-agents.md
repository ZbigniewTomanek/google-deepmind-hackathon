# Test Agents

Self-contained testing environment for NeoCortex memory capabilities. Uses [OpenAgentCompiler](https://github.com/...) to define AI agents in Python, compile them to OpenCode format, and run them via a FastAPI HTTP API. Agents interact with NeoCortex through MCP (Model Context Protocol) tools: `remember`, `recall`, `discover`.

```
test_agents/
    agents/          # Agent definitions (Python builders)
    agent_scripts/   # Tool implementations (ScriptTool subclasses)
    app/             # FastAPI service (HTTP API + agent runner)
    build/           # Generated output (gitignored) — compiled agents + scripts
    docker/          # Docker Compose (opencode-web + agent-api)
    examples/        # curl example scripts (.sh)
    build_agents.py  # Compilation entry point
    setup.sh         # One-time setup script
    run.py           # Uvicorn entry point
```

## Architecture

### System Diagram

```
                          Host Machine
 ┌──────────────────────────────────────────────────────────────┐
 │                                                              │
 │  curl / test script                                          │
 │       │                                                      │
 │       ▼                                                      │
 │  ┌─────────────────────┐   ┌──────────────────────────────┐  │
 │  │  agent-api (:8003)  │   │  opencode-web (:4098)        │  │
 │  │  FastAPI             │──▶│  OpenCode Web UI + Runtime   │  │
 │  │                     │   │                              │  │
 │  │  opencode run       │   │  Agent Markdown (.md)        │  │
 │  │    --attach :4098   │   │  opencode.json (config)      │  │
 │  └─────────────────────┘   └───────────┬──────────────────┘  │
 │                                        │                     │
 │                          ┌─────────────┼─────────────┐       │
 │                          │             │             │       │
 │                          ▼             ▼             ▼       │
 │                    bash: uv run   todoread/     MCP tools    │
 │                    scripts/*.py   todowrite   (neocortex)    │
 │                    (ScriptTools)               │             │
 │                                                ▼             │
 │                                         NeoCortex MCP        │
 │                                         (:8000)              │
 └──────────────────────────────────────────────────────────────┘
```

### Agent Hierarchy

```
chat (primary, temp=0.4)
├── search-orchestrator (subagent, temp=0.3)
│   ├── youtube-search-tool (ScriptTool)
│   └── google-search-tool (ScriptTool)
├── task-subagent (subagent, temp=0.2)
│   └── task-manager (ScriptTool)
└── joke-subagent (subagent, temp=0.7)
    └── joke-tool (ScriptTool)
```

The **chat** agent is the only primary agent. It classifies user intent (search / task / joke / general) and routes to the appropriate subagent via OpenCode's Task tool. Subagents execute their tools as bash commands (`uv run scripts/*.py --arg val`) and return JSON output.

### Data Flow

A request like `POST /agents/chat/run {"prompt": "Tell me a joke"}` follows this path:

1. **FastAPI** receives the request, creates a `SessionState` (in-memory)
2. **Context injection**: if `context` is provided, wraps it in `<CONVERSATION_HISTORY>` tags and prepends to the prompt
3. **Agent resolution**: maps `"chat"` to `build/.opencode/agents/chat.md`
4. **Subprocess**: launches `opencode run --attach http://localhost:4098 --agent chat "<prompt>"`
5. **OpenCode runtime** loads `chat.md`, reads its workflow steps
6. **Step 1**: Chat agent evaluates intent as `"joke"`
7. **Step 4**: Gate passes (`intent == "joke"`), invokes `joke-subagent` via Task tool
8. **Joke subagent** runs `uv run scripts/joke_tool.py --topic "..." --json` via bash
9. **ScriptTool** returns JSON: `{"joke": "...", "topic": "...", "style": "..."}`
10. **Chat agent** formats the joke and returns final output
11. **FastAPI** captures stdout, sets `status="completed"`, returns `AgentRunResponse`
12. **Session visible** in OpenCode Web UI at `http://localhost:4098`

## Quick Start

### Prerequisites

- Python 3.13+ with [uv](https://docs.astral.sh/uv/)
- Docker and Docker Compose
- [OpenCode](https://opencode.ai) binary installed (`~/.opencode/bin/opencode`)
- NeoCortex MCP server running on port 8000 (optional, for memory tools)

### Setup

```bash
cd test_agents
bash setup.sh
```

This script:
1. Creates `.env` from `.env.example` (if missing)
2. Symlinks `docker/.env -> ../.env` for Docker Compose variable substitution
3. Compiles agents into `build/` (creates `.opencode/agents/`, `opencode.json`, `scripts/`, git marker)

Edit `.env` with your API key:

```env
ZAI_API_KEY=your-key-here
PROJECT_ROOT=/absolute/path/to/google-deepmind-hackathon
OPENCODE_BIN=/home/you/.opencode/bin/opencode
```

### Running with Docker

```bash
cd test_agents/docker
docker compose up -d
```

Two services start:
- **opencode-web** on port 4098 — OpenCode web UI (session monitoring)
- **agent-api** on port 8003 — FastAPI HTTP API

### Running Locally (without Docker)

```bash
# Terminal 1: Start OpenCode web server
cd test_agents/build && opencode web --port 4098

# Terminal 2: Start FastAPI
cd test_agents && uv run python run.py
```

### Verify

```bash
# Health check
curl http://localhost:8003/health

# List agents
curl http://localhost:8003/agents

# Run a joke
curl -X POST http://localhost:8003/agents/chat/run \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Tell me a joke about programming"}'
```

## OpenAgentCompiler Framework

### Concepts

The framework has three layers:

| Layer | Format | Purpose |
|-------|--------|---------|
| **Agent definitions** | Python (builders) | Declarative agent construction |
| **Compiled agents** | Markdown + JSON + scripts | OpenCode-executable format |
| **Tool implementations** | Python (ScriptTool) | Bash-executable tools with Pydantic I/O |

You define agents in Python using fluent builder APIs. The compiler transforms them to OpenCode's native format (`.md` files with YAML frontmatter). At runtime, OpenCode reads these files, enforces permissions, and executes the workflow — including invoking bash commands that run your ScriptTool scripts.

### Builder API

#### ConfigBuilder — Provider and MCP setup

From `test_agents/agents/config.py`:

```python
from open_agent_compiler._types import (
    ModelConfig, ModelLimits, ModelOptions,
    ProviderConfig, ProviderOptions,
)
from open_agent_compiler.builders import ConfigBuilder

config = (
    ConfigBuilder()
    .provider(
        ProviderConfig(
            name="zai-coding-plan",
            options=ProviderOptions(
                api_key="env:ZAI_API_KEY",
                base_url="https://api.z.ai/api/coding/paas/v4",
                timeout=600000,
                max_retries=2,
            ),
            models=(
                ModelConfig(
                    name="glm-5",
                    id="glm-5",
                    limits=ModelLimits(context=131072, output=16384),
                    options=ModelOptions(temperature=0.3, top_p=0.9),
                ),
            ),
        )
    )
    .default_model("zai-coding-plan/glm-5")
    .mcp_server(name="neocortex", command="npx", args=["mcp-remote", mcp_url])
    .compaction(auto=True, prune=True)
    .build()
)
```

Key: `.mcp_server()` registers MCP servers. NeoCortex is connected via `mcp-remote` proxy, which provides `remember`, `recall`, and `discover` tools to all agents.

#### ToolBuilder — Linking to ScriptTool scripts

From `test_agents/agents/tools.py`:

```python
from open_agent_compiler.builders import ToolBuilder

def build_joke_tool():
    return (
        ToolBuilder()
        .name("joke-tool")
        .description("Generate a joke on a given topic and style")
        .from_script(str(SCRIPTS_DIR / "joke_tool.py"))
        .build()
    )
```

`.from_script()` introspects the `ScriptTool` subclass to extract Pydantic input/output models, then auto-generates CLI argument patterns and usage examples. The compiled agent will have bash permission to run `uv run scripts/joke_tool.py *`.

#### AgentBuilder — Defining an agent

From `test_agents/agents/joke.py` (simplest complete agent):

```python
from open_agent_compiler.builders import AgentBuilder, WorkflowStepBuilder

def build_joke_subagent(config):
    joke_tool = build_joke_tool()

    step = (
        WorkflowStepBuilder()
        .id("1").name("Generate Joke")
        .todo("Generate joke", "Create a joke using the joke tool")
        .use_tool("joke-tool")
        .instructions("Use the joke-tool with the requested topic and style.")
        .mark_done("Generate joke")
        .build()
    )

    return (
        AgentBuilder()
        .name("joke-subagent")
        .description("Tells funny jokes on any topic")
        .mode("subagent")         # Invocable by parent via Task tool
        .config(config)
        .tool(joke_tool)
        .preamble("# Joke Subagent\n\nGenerate a funny joke using the joke-tool.")
        .workflow_step(step)
        .temperature(0.7)         # Higher = more creative
        .build()
    )
```

Key builder methods:

| Method | Purpose |
|--------|---------|
| `.name(str)` | Agent identifier (becomes filename) |
| `.mode("primary"\|"subagent")` | Primary agents are top-level; subagents invoked via Task tool |
| `.config(AgentConfig)` | Provider, model, MCP servers |
| `.tool(ToolDefinition)` | Add a tool the agent can use |
| `.subagent(SubagentDefinition)` | Declare an invocable subagent |
| `.workflow_step(WorkflowStepDefinition)` | Add a mandatory workflow step |
| `.preamble(str)` | Content before workflow section in system prompt |
| `.temperature(float)` | Sampling temperature |
| `.steps(int)` | Max execution steps |
| `.permissions(AgentPermissions)` | Permission overrides |

#### WorkflowStepBuilder — Intent routing with evaluate/gate/route

From `test_agents/agents/chat.py` (primary agent routing):

```python
step_1 = (
    WorkflowStepBuilder()
    .id("1").name("Analyze Intent")
    .todo("Analyze intent", "Determine what the user wants")
    .evaluate("intent", "What is the user trying to do?",
              "search", "task", "joke", "general")
    .instructions("Determine intent: search, task, joke, or general.")
    .route("intent", "search", goto="2")
    .route("intent", "task", goto="3")
    .route("intent", "joke", goto="4")
    .route("intent", "general", goto="5")
    .mark_done("Analyze intent")
    .build()
)

step_2 = (
    WorkflowStepBuilder()
    .id("2").name("Search")
    .todo("Run search", "Delegate to search orchestrator")
    .gate("intent", "search")          # Only execute if intent == "search"
    .subagent("search-orchestrator")   # Invoke via Task tool
    .instructions("Invoke search-orchestrator with the user's query.")
    .mark_done("Run search")
    .build()
)
```

Pattern: Step 1 uses `.evaluate()` to classify intent, then `.route()` jumps to the matching step. Each subsequent step uses `.gate()` to conditionally execute only when its intent matches.

#### SubagentBuilder — Declaring invocable subagents

```python
search_ref = (
    SubagentBuilder()
    .name("search-orchestrator")
    .description("Searches YouTube and Google")
    .build()
)

AgentBuilder()
    .subagent(search_ref)   # Declare that this agent can invoke search-orchestrator
    ...
```

### Compilation Pipeline

```python
from open_agent_compiler.compiler import compile_agent
from open_agent_compiler.writers import OpenCodeWriter

compiled = compile_agent(agent_def, target="opencode")
writer = OpenCodeWriter(output_dir=Path("build/"), scripts_dir=Path("agent_scripts/"))
writer.write(compiled)
```

`compile_agent()` transforms the Python definition into a dict containing:
- System prompt (markdown with workflow steps, security policy, subagent docs)
- Permission model (what tools/bash patterns are allowed)
- Config (provider, model, MCP servers)
- Script file references

`OpenCodeWriter.write()` persists this to disk:
- `build/.opencode/agents/{name}.md` — agent definition with YAML frontmatter
- `build/opencode.json` — provider/model/MCP configuration
- `build/scripts/` — copied tool scripts + runtime infrastructure

### ScriptTool: Writing Tool Implementations

Tools are Python scripts based on `ScriptTool[Input, Output]`. The LLM agent runs them via bash (`uv run scripts/tool.py --args`).

From `test_agents/agent_scripts/joke_tool.py`:

```python
from pydantic import BaseModel, Field
from open_agent_compiler.runtime import ScriptTool

class JokeInput(BaseModel):
    topic: str = Field(default="programming", description="Topic for the joke")
    style: str = Field(default="pun", description="Style: pun, one-liner, knock-knock")

class JokeOutput(BaseModel):
    joke: str
    topic: str
    style: str

class JokeTool(ScriptTool[JokeInput, JokeOutput]):
    name = "joke-tool"
    description = "Generate a joke on a given topic and style"

    def execute(self, input: JokeInput) -> JokeOutput:
        # Your implementation here
        return JokeOutput(joke="...", topic=input.topic, style=input.style)

if __name__ == "__main__":
    JokeTool.run()
```

`ScriptTool.run()` auto-generates an argparse CLI from the Pydantic input model. The agent invokes it as:

```bash
uv run scripts/joke_tool.py --topic "AI" --style "pun"
# Output: {"joke": "...", "topic": "AI", "style": "pun"}
```

## Agent Definitions

| Agent | Mode | Temp | Tools | Purpose |
|-------|------|------|-------|---------|
| `chat` | primary | 0.4 | todoread, todowrite | Routes to subagents by intent |
| `search-orchestrator` | subagent | 0.3 | youtube-search-tool, google-search-tool | Searches YouTube and Google |
| `task-subagent` | subagent | 0.2 | task-manager | Todo list management |
| `joke-subagent` | subagent | 0.7 | joke-tool | Joke generation |

**Chat agent workflow**: Evaluate intent (search/task/joke/general) -> gate to matching step -> invoke subagent or respond directly. For general queries, can use NeoCortex MCP tools (remember, recall, discover).

**Primary vs subagent permissions**: Primary agents use OpenCode's built-in `todoread`/`todowrite` tools for progress tracking. Subagents use `subagent_todo.py` (file-based) since built-in todo tools are disabled for them.

Source files: `test_agents/agents/chat.py`, `search.py`, `task.py`, `joke.py`

## Tool Implementations

All tools are mock implementations with hardcoded data, suitable for testing without external API keys.

| Script | Input | Output | Notes |
|--------|-------|--------|-------|
| `joke_tool.py` | `topic`, `style` | `joke`, `topic`, `style` | Template jokes by style (pun, one-liner, etc.) |
| `youtube_search.py` | `query`, `max_results` | `results[]`, `query`, `total_found` | Mock video results, keyword-filtered |
| `google_search.py` | `query`, `max_results` | `results[]`, `query`, `total_found` | Mock web results, keyword-filtered |
| `task_manager.py` | `action`, `title`, `task_id` | `tasks[]`, `message` | File-based storage in `.agent_workspace/tasks.json` |

Additionally, the compiler copies infrastructure scripts to `build/scripts/`:
- `subagent_todo.py` — file-based progress tracking for subagents
- `opencode_manager.py` — opencode server management wrapper
- `workspace_io.py` — sandboxed file I/O

Source: `test_agents/agent_scripts/`

## FastAPI Service

### Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/agents` | List all compiled agents with metadata |
| `POST` | `/agents/{name}/run` | Run an agent (sync or async) |
| `GET` | `/sessions/{session_id}` | Poll session status and output |
| `POST` | `/agents/compile` | Force recompilation of all agents |
| `GET` | `/health` | Health check |

Interactive docs at `http://localhost:8003/docs`.

### Execution Modes

**Sync (default)** — waits for agent completion:

```bash
curl -X POST http://localhost:8003/agents/chat/run \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Tell me a joke"}'
# Returns: {"session_id": "...", "status": "completed", "output": "..."}
```

**Async** — returns immediately, poll for result:

```bash
# Fire
curl -X POST http://localhost:8003/agents/chat/run \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Tell me a joke", "async_mode": true}'
# Returns: {"session_id": "sess-abc123", "status": "running", "output": ""}

# Poll
curl http://localhost:8003/sessions/sess-abc123
# Returns: {"status": "completed", "output": "..."} (when done)
```

### Context Injection

Pass prepopulated conversation history via the `context` field. The agent runner wraps it in `<CONVERSATION_HISTORY>` tags that the chat agent's preamble recognizes:

```bash
curl -X POST http://localhost:8003/agents/chat/run \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "What did we discuss?",
    "context": [
      {"role": "user", "content": "My name is Alice"},
      {"role": "assistant", "content": "Nice to meet you, Alice!"}
    ]
  }'
```

The agent receives:
```
<CONVERSATION_HISTORY>
[USER]: My name is Alice
[ASSISTANT]: Nice to meet you, Alice!
</CONVERSATION_HISTORY>

Current request: What did we discuss?
```

### Callback Mechanism

Provide a `callback_url` to receive the full result asynchronously:

```bash
curl -X POST http://localhost:8003/agents/chat/run \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Tell me a joke", "callback_url": "http://localhost:9999/webhook"}'
```

When the agent completes, a POST is sent to the callback URL with:
```json
{
  "session_id": "...",
  "agent_name": "chat",
  "status": "completed",
  "output": "...",
  "full_context": [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}]
}
```

### Session Lifecycle

1. `POST /agents/{name}/run` creates a `SessionState` (in-memory, keyed by `session_id`)
2. Status transitions: `running` -> `completed` | `failed`
3. Sessions are ephemeral — lost on API restart
4. Sessions are also visible in the OpenCode Web UI at `http://localhost:4098`

Source: `test_agents/app/main.py`, `test_agents/app/agent_runner.py`

## Docker Setup

### Services

**opencode-web** (port 4098):
- Runs `opencode web --hostname 0.0.0.0 --port 4098`
- Mounts `build/` at `/app` (the OpenCode project root)
- Serves the web UI for monitoring sessions

**agent-api** (port 8003):
- Runs `uv sync && uv run python run.py`
- Mounts full project at `/workspace` and `build/` at `/app`
- Depends on opencode-web starting first

Both use `network_mode: host` to access NeoCortex MCP on `localhost:8000`.

### Volume Mounts

```yaml
# opencode-web
- ${PROJECT_ROOT}/test_agents/build:/app          # Compiled agents
- ${OPENCODE_BIN}:/usr/local/bin/opencode:ro      # OpenCode binary

# agent-api (additionally)
- ${PROJECT_ROOT}:/workspace                       # Full project for uv sync
```

### Environment Variables

```yaml
x-common-env:
  HOME: /home/appuser
  XDG_DATA_HOME: /app/.opencode/data       # OpenCode DB location
  XDG_CONFIG_HOME: /app/.opencode/config   # OpenCode config location
  UV_PROJECT_ENVIRONMENT: /tmp/.venv       # Ephemeral venv (avoids permission issues)
```

### Project Detection

OpenCode detects the project root by walking up to find a git repo. The build pipeline creates a minimal git repo in `build/` (`_ensure_build_scaffold()`) so OpenCode correctly identifies `/app` as the project root inside Docker. Without this, OpenCode falls back to `/` and agents aren't found.

### .env Symlink

Docker Compose reads `.env` from the same directory as `docker-compose.yml` for variable substitution (`${PROJECT_ROOT}`, `${OPENCODE_BIN}`). The setup script creates a symlink `docker/.env -> ../.env` so you only maintain one `.env` file.

## Build Pipeline

### setup.sh

```bash
cd test_agents && bash setup.sh
```

1. Creates `.env` from `.env.example` (if missing)
2. Symlinks `docker/.env -> ../.env`
3. Runs `uv run python build_agents.py` to compile agents

### compile_and_write()

In `test_agents/build_agents.py`:

1. `build_config()` — creates shared provider/MCP config
2. Builds 4 agent definitions (chat, search-orchestrator, task-subagent, joke-subagent)
3. For each: `compile_agent(def, target="opencode")` -> `OpenCodeWriter.write(compiled)`
4. `_ensure_build_scaffold()` — writes `pyproject.toml` (with pydantic + open-agent-compiler deps) and initializes git repo

### Compiled Output

```
build/
    .git/                          # Project marker for OpenCode
    .gitignore                     # * (ignore everything)
    .opencode/
        agents/
            chat.md                # Primary agent
            search-orchestrator.md # Subagent
            task-subagent.md       # Subagent
            joke-subagent.md       # Subagent
        data/opencode/             # OpenCode DB, logs (runtime)
    scripts/
        joke_tool.py               # Copied from agent_scripts/
        youtube_search.py
        google_search.py
        task_manager.py
        subagent_todo.py           # From OpenAgentCompiler package
        opencode_manager.py        # From OpenAgentCompiler package
        workspace_io.py            # From OpenAgentCompiler package
    opencode.json                  # Provider/model/MCP config
    pyproject.toml                 # Dependencies for uv run inside build/
```

## How-To Guides

### Adding a New Tool

1. Create `test_agents/agent_scripts/my_tool.py`:

```python
from pydantic import BaseModel, Field
from open_agent_compiler.runtime import ScriptTool

class MyInput(BaseModel):
    query: str = Field(description="The input query")

class MyOutput(BaseModel):
    result: str

class MyTool(ScriptTool[MyInput, MyOutput]):
    name = "my-tool"
    description = "Does something useful"

    def execute(self, input: MyInput) -> MyOutput:
        return MyOutput(result=f"Processed: {input.query}")

if __name__ == "__main__":
    MyTool.run()
```

2. Register in `test_agents/agents/tools.py`:

```python
def build_my_tool():
    return (
        ToolBuilder()
        .name("my-tool")
        .description("Does something useful")
        .from_script(str(SCRIPTS_DIR / "my_tool.py"))
        .build()
    )
```

3. Add to the relevant agent builder (e.g., `agents/chat.py` or a new subagent)
4. Recompile: `cd test_agents && uv run python build_agents.py`

### Adding a New Subagent

1. Create `test_agents/agents/my_agent.py`:

```python
from open_agent_compiler.builders import AgentBuilder, WorkflowStepBuilder
from agents.tools import build_my_tool

def build_my_agent(config):
    my_tool = build_my_tool()

    step = (
        WorkflowStepBuilder()
        .id("1").name("Do Work")
        .todo("Do work", "Execute the main task")
        .use_tool("my-tool")
        .instructions("Use my-tool to process the request.")
        .mark_done("Do work")
        .build()
    )

    return (
        AgentBuilder()
        .name("my-agent")
        .description("My custom subagent")
        .mode("subagent")
        .config(config)
        .tool(my_tool)
        .preamble("# My Agent\n\nProcess requests using my-tool.")
        .workflow_step(step)
        .temperature(0.3)
        .build()
    )
```

2. Export from `test_agents/agents/__init__.py`:

```python
from agents.my_agent import build_my_agent
```

3. Add to `test_agents/build_agents.py`:

```python
agents = [
    build_chat(config),
    build_search_orchestrator(config),
    build_task_subagent(config),
    build_joke_subagent(config),
    build_my_agent(config),       # New
]
```

4. Register as a subagent in the parent (e.g., `agents/chat.py`):

```python
my_ref = SubagentBuilder().name("my-agent").description("My custom agent").build()
# ...
AgentBuilder()
    .subagent(my_ref)
    # Add a workflow step with .gate() and .subagent("my-agent") for routing
```

5. Recompile and restart Docker

### Replacing Mock Tools with Real APIs

The mock tools (youtube_search, google_search) have hardcoded results. To use real APIs, replace the `execute()` method while keeping the same Input/Output models:

```python
class YouTubeSearchTool(ScriptTool[YouTubeSearchInput, YouTubeSearchOutput]):
    def execute(self, input: YouTubeSearchInput) -> YouTubeSearchOutput:
        # Replace mock data with real API call
        import googleapiclient.discovery
        youtube = googleapiclient.discovery.build("youtube", "v3", developerKey="...")
        response = youtube.search().list(q=input.query, maxResults=input.max_results).execute()
        results = [{"title": item["snippet"]["title"], ...} for item in response["items"]]
        return YouTubeSearchOutput(results=results, query=input.query, total_found=len(results))
```

Add any new dependencies to the `_BUILD_PYPROJECT` constant in `build_agents.py` so they're available inside the Docker container.

### Customizing the LLM Provider

Edit `test_agents/agents/config.py`. The `ConfigBuilder` supports any OpenAI-compatible API:

```python
.provider(
    ProviderConfig(
        name="my-provider",
        options=ProviderOptions(
            api_key="env:MY_API_KEY",
            base_url="https://api.example.com/v1",
        ),
        models=(
            ModelConfig(name="my-model", id="model-id-here", ...),
        ),
    )
)
.default_model("my-provider/my-model")
```

## Compiled Output Reference

### Agent Markdown Format

Each compiled agent is a markdown file with YAML frontmatter:

```yaml
---
description: Tells funny jokes on any topic
model: zai-coding-plan/glm-5
mode: subagent
temperature: 0.7
tool:
  bash:
    "*": deny
    "uv run scripts/joke_tool.py *": allow
    "uv run scripts/subagent_todo.py *": allow
  read: false
  write: false
  task: false
  todoread: false
  todowrite: false
  mcp: false
permission:
  "*": deny
  bash:
    "*": deny
    "uv run scripts/joke_tool.py *": allow
    "uv run scripts/subagent_todo.py *": allow
---
# System prompt content here...
```

### Permission Model

Two sections control what an agent can do:

- **`tool:`** — What the LLM *sees* (model visibility). Controls which tools appear in the model's tool list. Not enforced at runtime.
- **`permission:`** — What the LLM *can execute* (runtime enforcement). Always enforced by OpenCode. Global `"*": deny` blocks everything by default.

Bash permissions use glob patterns: `"uv run scripts/joke_tool.py *": allow` permits the agent to run that specific script with any arguments.

### Todo Tracking

- **Primary agents** (chat): Use OpenCode's built-in `todoread` and `todowrite` tools
- **Subagents**: Use `subagent_todo.py` (file-based JSON in `.agent_todos/`) because built-in todo tools are disabled for them

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `opencode CLI not found` | Install opencode, set `OPENCODE_BIN` in `.env`. The API falls back to direct tool execution but without full agent orchestration. |
| Agent not found (404) | Check `build/.opencode/agents/` for the `.md` file. Recompile: `POST /agents/compile` or re-run `setup.sh`. |
| Timeout (300s) | Configurable in `app/agent_runner.py` line 139. Agent chains with multiple subagent calls can be slow. |
| Sessions not visible in web UI | Ensure `build/.git` exists (opencode project detection). Verify `opencode debug scrap` shows `/app` as project. |
| Missing deps in Docker (`ModuleNotFoundError`) | Add dependency to `_BUILD_PYPROJECT` in `build_agents.py`, recompile, and restart containers. |
| Docker `PROJECT_ROOT` not set | Ensure `docker/.env` symlink exists: `ln -s ../.env docker/.env` |
| Stale agents after code changes | Recompile: `uv run python build_agents.py` then `docker compose restart` |
