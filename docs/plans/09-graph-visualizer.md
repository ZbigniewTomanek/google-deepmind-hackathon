# Plan: Graph Visualizer React App

## Overview

Build a React app that visualizes two layers of NeoCortex data:
1. **Agent hierarchy graph** — parsed from compiled `.md` files, showing which agent can call which subagent
2. **Per-agent knowledge graph** — nodes and edges stored in the NeoCortex PostgreSQL database, displayed when clicking on an agent in the hierarchy

The app lives in `graph-visualizer/` at the project root. Backend API endpoints are added to the existing FastAPI ingestion app.

## Design Constraints

- **Minimal changes to existing code** — no modifications to `MemoryRepository` protocol, services, or existing routes. Read-only SQL via `schema_scoped_connection` is acceptable.
- **Fully dynamic** — agents directory is configurable (no hardcoded paths), schema list comes from `graph_registry` at query time, agent-to-schema mapping resolved by the backend.
- **Local-only debug tool** — no auth, no permission checks. CORS always on for Vite dev server.
- **Graceful in mock mode** — endpoints return empty data when `schema_mgr is None`, never crash.

## Data Sources

### Agent definitions (`.md` files)
- Location: configurable via `agents_dir` setting (default: `test_agents/build/.opencode/agents/`)
- Structure: YAML frontmatter with `mode: primary|subagent`, `description`, `model`, `temperature`
- Subagent references: `subagent_type: "agent-name"` in the markdown body
- MCP server names in `permission` block (e.g., `neocortex-chat*`, `neocortex-joke*`) — these map to agent IDs in the database

### Knowledge graph (PostgreSQL)
- Schemas: `ncx_{agent_id}__personal` (e.g., `ncx_chat__personal`, `ncx_joke__personal`)
- Tables per schema: `node`, `edge`, `node_type`, `edge_type`, `episode`
- Schema list comes dynamically from `graph_registry` table — never inferred from naming conventions

## Architecture

```
┌─────────────────────────────────────────────────┐
│  graph-visualizer/  (Vite + React + TypeScript)  │
│                                                   │
│  ┌──────────────┐      ┌───────────────────────┐ │
│  │ AgentGraph    │─────▶│ KnowledgeGraph        │ │
│  │ (hierarchy)   │click │ (nodes/edges from DB) │ │
│  └──────────────┘      └───────────────────────┘ │
│         │                        │                │
│         ▼                        ▼                │
│    GET /api/viz/agents    GET /api/viz/graphs/    │
│                           {schema}/data           │
└─────────────────────────────────────────────────┘
         │                        │
         ▼                        ▼
┌─────────────────────────────────────────────────┐
│  FastAPI ingestion app (:8001)                    │
│                                                   │
│  /api/viz/agents      → parse .md files → JSON   │
│  /api/viz/graphs      → list from graph_registry │
│  /api/viz/graphs/{s}/data → nodes + edges → JSON │
└─────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────┐
│  PostgreSQL (ncx_*__* schemas)                    │
└─────────────────────────────────────────────────┘
```

## Execution Protocol

For each stage:
1. Read the stage steps
2. Implement each step
3. Run verification checks
4. Update the progress tracker
5. Commit with the specified message
6. Proceed to next stage

---

## Stage 1: Backend Visualization API Endpoints

**Goal**: Add `/api/viz/*` endpoints to the existing FastAPI ingestion app that serve agent hierarchy and graph data as JSON.

### Steps

1. **Create `src/neocortex/viz/` module** with:
   - `__init__.py` (empty)
   - `agent_parser.py` — function to parse all `.md` files in a given directory:
     - Read each `.md` file, split on `---` to extract YAML frontmatter (manual split, no `pyyaml` dependency)
     - Extract: `name` (filename without `.md`), `description`, `mode`, `model`, `temperature`
     - Extract MCP server names from `permission` block keys matching `neocortex-*` (strip trailing `*`)
     - Scan markdown body for `subagent_type: "agent-name"` patterns → list of subagent names
     - Return list of `AgentDefinition` dicts
     - If directory doesn't exist, return empty list (no crash)
   - `routes.py` — FastAPI router with prefix `/api/viz`

2. **Endpoint: `GET /api/viz/agents`**
   - Reads `agents_dir` from `request.app.state.settings` (falls back to default)
   - Calls `agent_parser.parse_agents(directory)`
   - Enriches each agent with `schemas` field: queries `graph_registry` to find schemas whose `agent_id` matches any MCP server name's derived agent ID (e.g., `neocortex-chat` → agent_id `chat`)
   - If `schema_mgr is None` (mock mode): `schemas` is empty list
   - Response shape:
     ```json
     {
       "agents": [
         {
           "name": "chat-with-memory",
           "description": "Memory-first chat agent...",
           "mode": "primary",
           "model": "zai-coding-plan/glm-5",
           "temperature": 0.4,
           "mcp_servers": ["neocortex-chat"],
           "subagents": ["joke-with-memory"],
           "schemas": ["ncx_chat__personal"]
         }
       ],
       "edges": [
         {"from": "chat-with-memory", "to": "joke-with-memory"}
       ]
     }
     ```

3. **Endpoint: `GET /api/viz/graphs`**
   - Lists all registered graph schemas with stats from `graph_registry`
   - If `schema_mgr is None` (mock mode): return empty list
   - Uses `schema_mgr.list_graphs()` — no new SQL needed
   - Response: list of `{schema_name, agent_id, purpose, is_shared, created_at}`

4. **Endpoint: `GET /api/viz/graphs/{schema_name}/data`**
   - Validates schema_name matches `^ncx_[a-z0-9]+__[a-z0-9_]+$`
   - If `schema_mgr is None` (mock mode): return 404 "No database available"
   - Accepts query params: `node_limit` (default 500), `edge_limit` (default 1000)
   - Queries the schema directly via `schema_scoped_connection`:
     ```sql
     SELECT n.id, n.name, n.content, nt.name as type_name, n.properties,
            n.importance, n.access_count, n.forgotten
     FROM node n JOIN node_type nt ON n.type_id = nt.id
     WHERE n.forgotten = false
     ORDER BY n.importance DESC, n.access_count DESC
     LIMIT $1

     SELECT e.id, e.source_id, e.target_id, et.name as type_name,
            e.weight, e.properties
     FROM edge e JOIN edge_type et ON e.type_id = et.id
     ORDER BY e.weight DESC
     LIMIT $1
     ```
   - Also queries total counts (without LIMIT) for the stats object
   - Response shape:
     ```json
     {
       "schema_name": "ncx_chat__personal",
       "nodes": [
         {"id": 1, "name": "Python", "type": "Tool", "content": "...", "properties": {}, "importance": 0.8, "access_count": 5}
       ],
       "edges": [
         {"id": 1, "source_id": 1, "target_id": 2, "type": "USES", "weight": 1.0, "properties": {}}
       ],
       "stats": {"total_nodes": 42, "total_edges": 78, "node_limit": 500, "edge_limit": 1000}
     }
     ```

5. **Register the router** in `src/neocortex/ingestion/app.py`:
   - `from neocortex.viz.routes import router as viz_router`
   - `app.include_router(viz_router)`
   - Add CORS middleware for `localhost:5173` (Vite dev server)

6. **Add `agents_dir` to `MCPSettings`** (optional str, default `""` meaning auto-detect from project root / `test_agents/build/.opencode/agents/`)

### Verification
- `uv run pytest tests/ -v` — existing tests still pass
- `NEOCORTEX_MOCK_DB=true uv run python -m neocortex.ingestion` → start server
  - `curl http://localhost:8001/api/viz/agents` → valid JSON with agents and empty schemas
  - `curl http://localhost:8001/api/viz/graphs` → empty list
  - `curl http://localhost:8001/api/viz/graphs/ncx_chat__personal/data` → 404 mock mode message
- With real DB: `curl http://localhost:8001/api/viz/graphs` → lists from graph_registry

### Commit
```
feat(viz): add visualization API endpoints for agent hierarchy and graph data
```

---

## Stage 2: React App Scaffold

**Goal**: Create a new Vite + React + TypeScript app in `graph-visualizer/` with React Flow and Tailwind CSS.

### Steps

1. **Scaffold the React app**:
   ```bash
   cd /home/dw/programing/google-deepmind-hackathon
   npm create vite@latest graph-visualizer -- --template react-ts
   cd graph-visualizer
   npm install
   ```

2. **Install dependencies**:
   ```bash
   npm install @xyflow/react
   npm install -D tailwindcss @tailwindcss/vite
   ```

3. **Configure Tailwind** in `vite.config.ts`:
   ```ts
   import tailwindcss from "@tailwindcss/vite";
   // add to plugins array
   ```
   Add `@import "tailwindcss"` to `src/index.css`.

4. **Configure Vite proxy** in `vite.config.ts`:
   ```ts
   server: {
     proxy: {
       '/api': 'http://localhost:8001'
     }
   }
   ```

5. **Create directory structure**:
   ```
   graph-visualizer/src/
     api/            # API client functions
       client.ts     # fetch wrappers for /api/viz/*
     components/     # React components
       AgentGraph.tsx
       KnowledgeGraph.tsx
       Layout.tsx
     types/          # TypeScript interfaces
       index.ts
     App.tsx
     main.tsx
     index.css
   ```

6. **Create `src/types/index.ts`** with TypeScript interfaces matching API responses:
   ```ts
   export interface AgentDefinition {
     name: string;
     description: string;
     mode: "primary" | "subagent";
     model: string;
     temperature: number;
     mcp_servers: string[];
     subagents: string[];
     schemas: string[];
   }
   export interface AgentHierarchy {
     agents: AgentDefinition[];
     edges: { from: string; to: string }[];
   }
   export interface GraphNode { id: number; name: string; type: string; content: string; properties: Record<string, unknown>; importance: number; access_count: number; }
   export interface GraphEdge { id: number; source_id: number; target_id: number; type: string; weight: number; properties: Record<string, unknown>; }
   export interface GraphData { schema_name: string; nodes: GraphNode[]; edges: GraphEdge[]; stats: { total_nodes: number; total_edges: number; node_limit: number; edge_limit: number }; }
   ```

7. **Create `src/api/client.ts`** with fetch functions:
   ```ts
   export async function fetchAgents(): Promise<AgentHierarchy> { ... }
   export async function fetchGraphs(): Promise<GraphInfo[]> { ... }
   export async function fetchGraphData(schema: string, nodeLimit?: number, edgeLimit?: number): Promise<GraphData> { ... }
   ```

8. **Create basic `App.tsx`** with two-panel layout:
   - Left panel: agent hierarchy (default view)
   - Right panel / overlay: knowledge graph (shown on agent click)
   - Use React state to track selected agent

9. **Add `graph-visualizer/node_modules/` and `graph-visualizer/dist/` to `.gitignore`**

### Verification
- `cd graph-visualizer && npm run build` — builds without errors
- `npm run dev` — starts on localhost:5173
- Types match API response shapes

### Commit
```
feat(viz): scaffold React app with React Flow and Tailwind
```

---

## Stage 3: Agent Hierarchy View

**Goal**: Render an interactive directed graph showing agents and their subagent relationships.

### Steps

1. **Implement `AgentGraph.tsx`**:
   - Fetch agents from `/api/viz/agents` on mount
   - Convert to React Flow nodes and edges:
     - Primary agents → larger nodes, colored by their `color` field or a default
     - Subagents → smaller nodes, different color
     - Edges → directed arrows from parent to subagent
   - Use `dagre` or manual layout for hierarchical positioning (primary agents at top, subagents below)
   - Node label: agent name + description snippet
   - On node click: if agent has `schemas` entries, emit `onAgentSelect(agentName, schemas)` callback

2. **Install dagre for layout** (optional, or do manual hierarchical positioning):
   ```bash
   npm install @dagrejs/dagre
   ```

3. **Node styling**:
   - Primary agents: rounded rectangle, green/olive tint, larger
   - Subagents: rounded rectangle, blue/gray tint, smaller
   - Show agent `mode` as a badge
   - Show MCP server names as small tags below the name
   - Visual indicator (dot/icon) on nodes that have `schemas` (clickable for graph view)

4. **Edge styling**:
   - Animated dashed edges for subagent calls
   - Label: "subagent call"

5. **Controls**:
   - React Flow MiniMap + Controls (zoom, pan)
   - Legend showing node types

6. **Wire up in `App.tsx`**:
   - Render `AgentGraph` as the main view
   - Pass `onAgentSelect` handler that sets selected agent + schema state

### Verification
- Start backend: `NEOCORTEX_MOCK_DB=true uv run python -m neocortex.ingestion`
- Start frontend: `cd graph-visualizer && npm run dev`
- Visit `localhost:5173` → see agent hierarchy graph with agents and correct edges
- Clicking a node logs the agent name and schemas to console

### Commit
```
feat(viz): implement agent hierarchy graph view with React Flow
```

---

## Stage 4: Knowledge Graph View

**Goal**: When clicking an agent that has schemas, fetch and render its knowledge graph from the database.

### Steps

1. **Implement `KnowledgeGraph.tsx`**:
   - Props: `schemaName: string`, `onBack: () => void`
   - Fetch graph data from `/api/viz/graphs/{schema}/data` on mount / when schema changes
   - Convert to React Flow nodes and edges:
     - Nodes: colored by `type` (Concept=blue, Person=green, Tool=purple, etc.)
     - Node size: scaled by `importance` or `access_count`
     - Edges: labeled with `type`, thickness scaled by `weight`
   - Use force-directed or dagre layout
   - Show stats panel: total nodes, edges + truncation info from `node_limit`/`edge_limit`

2. **Node detail panel**:
   - Click a node → show sidebar/tooltip with: name, type, content, properties, importance, access_count
   - Highlight connected edges on hover

3. **Graph info header**:
   - Schema name, agent name
   - Stats: node count, edge count (with "showing X of Y" when truncated)
   - Back button to return to agent hierarchy

4. **Handle empty/missing graphs**:
   - If no nodes/edges: show "No knowledge graph data yet" message
   - If schema doesn't exist or mock mode 404: show appropriate message

5. **Wire up in `App.tsx`**:
   - When agent is selected, use the `schemas` array from the agents response directly
   - If agent has multiple schemas, show a picker; if one, go straight to it
   - Back button returns to `AgentGraph`

6. **Color palette for node types** — create a `src/utils/colors.ts` mapping:
   ```ts
   const NODE_COLORS: Record<string, string> = {
     Concept: "#60a5fa",
     Person: "#34d399",
     Tool: "#a78bfa",
     Event: "#fbbf24",
     Document: "#f87171",
     Preference: "#f472b6",
   };
   // Fallback color for unknown types
   export function getNodeColor(type: string): string {
     return NODE_COLORS[type] ?? "#94a3b8";
   }
   ```

### Verification
- Start full stack: `./scripts/launch.sh` (with real DB that has some data)
- Click on `chat-with-memory` → should load knowledge graph for `ncx_chat__personal`
- Nodes and edges render with correct types and labels
- Back button returns to hierarchy view
- Also verify with mock DB: agent click shows "No knowledge graph data" gracefully

### Commit
```
feat(viz): implement per-agent knowledge graph view
```

---

## Stage 5: Polish & Integration

**Goal**: Loading states, error handling, layout tuning, and final integration testing.

### Steps

1. **Loading states**:
   - Spinner/skeleton while fetching agents
   - Spinner while fetching graph data
   - Use simple `isLoading` state

2. **Error handling**:
   - Network errors → show error message with retry button
   - Empty data → show informative message
   - Invalid schema → show "Graph not found"

3. **Layout improvements**:
   - Responsive layout — full-screen graph with floating panels
   - Smooth transitions between hierarchy and knowledge graph views
   - Auto-fit view on data load (`fitView` in React Flow)

4. **Add startup instructions to `graph-visualizer/README.md`**:
   ```
   cd graph-visualizer && npm install && npm run dev
   # Requires backend: NEOCORTEX_MOCK_DB=true uv run python -m neocortex.ingestion
   ```

### Verification
- Full flow: start backend → start frontend → see hierarchy → click agent → see knowledge graph → back → click another agent
- Works with mock DB (empty graphs, no crashes)
- Works with real DB (populated graphs)
- `npm run build` produces clean production build
- No console errors

### Commit
```
feat(viz): polish graph visualizer with loading states and error handling
```

---

## Progress Tracker

| Stage | Description | Status | Notes |
|-------|-------------|--------|-------|
| 1 | Backend visualization API endpoints | PENDING | |
| 2 | React app scaffold | PENDING | |
| 3 | Agent hierarchy view | PENDING | |
| 4 | Knowledge graph view | PENDING | |
| 5 | Polish & integration | PENDING | |

**Last stage completed**: —
**Last updated by**: —
