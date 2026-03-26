# NeoCortex: Agent Memory System - Hackathon Plan

## Vision

MCP server providing advanced, structured long-term memory for AI agents. Built on PostgreSQL with a graph data model using normalized relational tables. Agents get episodic, personal, and shared memory with evolving ontologies — all discoverable via MCP tools.

## Architecture Overview

```
                     +------------------+
                     |   Demo Agent(s)  |  (Pydantic AI + Gemini)
                     |  Claude / other  |
                     +--------+---------+
                              |  MCP protocol
                     +--------v---------+
                     |   MCP Server     |
                     |  (memory tools)  |
                     +--------+---------+
                              |
              +---------------+---------------+
              |                               |
     +--------v---------+           +--------v---------+
     | Ingestion API    |           | Query Engine     |
     | (streams/docs)   |           | (recall/discover)|
     +--------+---------+           +--------+---------+
              |                               |
     +--------v-------------------------------v---------+
     |              PostgreSQL                           |
     |  graph schema + pgvector + tsvector (BM25)       |
     +--------------------------------------------------+
```

## Data Model: Graph in PostgreSQL

Knowledge graph represented via normalized relational tables. Nodes are entities, edges are links. Ontology (schema) is stored alongside data so agents can discover what types of knowledge exist.

### Core Tables

```sql
-- What types of nodes exist (ontology)
CREATE TABLE node_type (
    id          SERIAL PRIMARY KEY,
    name        TEXT UNIQUE NOT NULL,       -- e.g. "Person", "Concept", "Document"
    description TEXT,
    created_at  TIMESTAMPTZ DEFAULT now()
);

-- What types of edges exist (ontology)
CREATE TABLE edge_type (
    id          SERIAL PRIMARY KEY,
    name        TEXT UNIQUE NOT NULL,       -- e.g. "MENTIONS", "CAUSED_BY", "AUTHORED"
    description TEXT,
    created_at  TIMESTAMPTZ DEFAULT now()
);

-- Nodes (entities/memories)
CREATE TABLE node (
    id          SERIAL PRIMARY KEY,
    type_id     INT REFERENCES node_type(id),
    name        TEXT NOT NULL,
    content     TEXT,                        -- main text content
    properties  JSONB DEFAULT '{}',          -- flexible key-value attributes
    embedding   vector(768),                 -- pgvector for semantic search
    tsv         tsvector GENERATED ALWAYS AS (to_tsvector('english', coalesce(name,'') || ' ' || coalesce(content,''))) STORED,
    source      TEXT,                        -- where this came from (agent_id, ingestion source)
    created_at  TIMESTAMPTZ DEFAULT now()
);

-- Edges (relationships between nodes)
CREATE TABLE edge (
    id          SERIAL PRIMARY KEY,
    source_id   INT REFERENCES node(id),
    target_id   INT REFERENCES node(id),
    type_id     INT REFERENCES edge_type(id),
    weight      FLOAT DEFAULT 1.0,
    properties  JSONB DEFAULT '{}',
    created_at  TIMESTAMPTZ DEFAULT now()
);

-- Episodic memory log (raw, append-only)
CREATE TABLE episode (
    id          SERIAL PRIMARY KEY,
    agent_id    TEXT NOT NULL,
    content     TEXT NOT NULL,
    embedding   vector(768),
    source_type TEXT,                        -- "chat", "obsidian", "git", "document"
    metadata    JSONB DEFAULT '{}',
    created_at  TIMESTAMPTZ DEFAULT now()
);

-- Indexes
CREATE INDEX idx_node_embedding ON node USING ivfflat (embedding vector_cosine_ops);
CREATE INDEX idx_node_tsv ON node USING GIN (tsv);
CREATE INDEX idx_edge_source ON edge (source_id);
CREATE INDEX idx_edge_target ON edge (target_id);
CREATE INDEX idx_episode_agent ON episode (agent_id, created_at DESC);
```

### Search Capabilities

- **Semantic**: pgvector cosine similarity on `node.embedding`
- **Lexical**: tsvector + GIN index for full-text search
- **Graph traversal**: JOINs on `edge` table
- **Hybrid recall**: combine vector similarity + text rank + graph proximity

## MCP Tools (agent-facing)

Toole na wysokim poziomie abstrakcji — agent opisuje *co* chce zapamiętać lub przywołać w języku naturalnym. Nie operuje bezpośrednio na grafie.

| Tool | Input | Opis |
|------|-------|------|
| `remember` | `text`: string, `context?`: string | "Zapamiętaj to." Agent podaje treść w języku naturalnym. System persystuje jako epizod, a wewnętrzni agenci asynchronicznie ekstrahują fakty do grafu |
| `recall` | `query`: string, `limit?`: int | "Co wiesz o X?" Hybrid search (semantic + lexical + graph) zwraca ranked wyniki z provenance |
| `discover` | `query?`: string | "Jakie rodzaje wiedzy masz?" Zwraca ontologię — typy bytów, relacje, statystyki. Opcjonalnie filtrowane po query |

3 toole. Tyle widzi agent. Reszta dzieje się pod spodem.

## Wewnętrzni agenci (backend, niewidoczni dla usera)

Za parsowanie danych, tworzenie ontologii i ekstrakcję faktów odpowiadają wyspecjalizowani agenci wewnętrzni. Uruchamiani asynchronicznie po każdym `remember` lub ingestion.

```
Agent wysyła "remember"
    │
    ▼
┌─────────────────────────────────┐
│  MCP Server                     │
│  1. Zapisz surowy epizod        │
│  2. Odpal pipeline agentów ───────────┐
│  3. Zwróć potwierdzenie agentowi│     │
└─────────────────────────────────┘     │
                                        ▼
                          ┌──────────────────────────┐
                          │  Ontology Agent           │
                          │  - analizuje treść        │
                          │  - proponuje nowe typy    │
                          │    jeśli nie pasuje do     │
                          │    istniejącej ontologii   │
                          └────────────┬─────────────┘
                                       ▼
                          ┌──────────────────────────┐
                          │  Extraction Agent         │
                          │  - wyciąga fakty z treści │
                          │    zgodnie z ontologią    │
                          │  - tworzy nodes + edges   │
                          └────────────┬─────────────┘
                                       ▼
                          ┌──────────────────────────┐
                          │  Librarian Agent          │
                          │  - deduplikacja           │
                          │  - merge z istniejącymi   │
                          │    nodes                  │
                          │  - normalizacja           │
                          └──────────────────────────┘
```

Agenci wewnętrzni mają pełny dostęp do grafu (CRUD na node/edge/type). Agent zewnętrzny (user-facing) — nie.

## Ingestion API (separate from MCP)

REST endpoints do ładowania danych strumieniami. Uruchamiają ten sam pipeline agentów co `remember`.

| Endpoint | Input | Processing |
|----------|-------|------------|
| `POST /ingest/text` | Raw text + metadata | Chunk -> episodes -> agent pipeline |
| `POST /ingest/document` | File (md, txt, pdf) | Parse -> chunk -> episodes -> agent pipeline |
| `POST /ingest/events` | JSON event stream | Map events -> episodes -> agent pipeline |
| `POST /ingest/obsidian` | Obsidian vault path | Parse markdown + wikilinks -> episodes -> agent pipeline |
| `POST /ingest/git` | Repo path + range | Parse commits/diffs -> episodes -> agent pipeline |

## Demo Use Case: Personal Knowledge Agent

**Scenario**: "Research Assistant" agent that has ingested:
- Obsidian notes about a topic
- Git repo activity
- Chat conversation history
- Research documents

**Demo flow**:
1. Ingest sample data from multiple sources (Obsidian vault, git log, documents)
2. Show ontology auto-discovery (what node/edge types were found)
3. Agent queries its memory: "What do I know about X?"
4. Agent traverses the graph: "How is concept A related to concept B?"
5. Agent recalls episodic context: "What did we discuss about X last time?"
6. Show cross-source connections (e.g., a concept from notes linked to a code change)

## Memory Types

Każdy agent podłączony do MCP serwera operuje na kilku warstwach pamięci. Warstwy różnią się zakresem (prywatna vs współdzielona), trwałością i sposobem zapisu.

### Per-Agent (prywatne)

```
Agent "research-bot"
├── Episodic Memory (episode table, agent_id = "research-bot")
│   ├── surowy log wszystkiego co agent widział/zrobił
│   ├── append-only, chronologiczny
│   └── źródła: chat, tool calls, obserwacje
│
├── Personal Memory (node/edge z source = "research-bot")
│   ├── wyekstrahowane fakty, preferencje, wnioski agenta
│   ├── "wiem, że użytkownik preferuje X"
│   ├── "nauczyłem się, że Y prowadzi do Z"
│   └── prywatny podgraf — inni agenci nie widzą
│
└── Working Context (nie persystowany — w kontekście LLM)
    └── bieżące zadanie, krótkoterminowe notatki
```

### Współdzielone (shared knowledge graph)

```
Shared Graph (node/edge bez ograniczenia source)
├── Semantic Memory — fakty o świecie
│   ├── "PostgreSQL wspiera pgvector od v16"
│   ├── "Projekt X zależy od biblioteki Y"
│   └── wyekstrahowane z dokumentów, repo, research
│
├── Ontology — schemat wiedzy (node_type, edge_type)
│   ├── jakie typy bytów istnieją
│   ├── jakie relacje są dozwolone
│   └── ewoluuje z napływem danych
│
└── Temporal Context — zdarzenia osadzone w czasie
    ├── "commit abc123 z 2026-03-25 zmienił moduł auth"
    ├── "spotkanie o X odbyło się 2026-03-20"
    └── umożliwia zapytania temporalne ("co się zmieniło od ostatniego tygodnia?")
```

### Przepływ danych między warstwami

```
Ingestion (docs, git, chat, obsidian)
    │
    ▼
Episode (surowy log, per agent)
    │
    ▼  LLM extraction
Nodes + Edges (shared graph)
    │
    ▼  ontology matching
Node Types / Edge Types (ontology evolves)
    │
    ▼  heuristics (async)
Consolidation, scoring, pruning
```

## Heuristics Roadmap

Heurystyki operujące na grafie pamięci — od najprostszych (hackathon MVP) do zaawansowanych (post-hackathon).

### Tier 1: Hackathon MVP
| Heurystyka | Opis | Implementacja |
|------------|------|---------------|
| **Recency bias** | Nowsze wspomnienia rankowane wyżej | `ORDER BY created_at DESC` z wagą w hybrid recall |
| **Frequency counting** | Ile razy node był przywoływany (read count) | Kolumna `access_count` na `node`, inkrementowana przy `recall`/`get_node` |
| **Hybrid scoring** | Łączenie vector similarity + BM25 + recency w jeden score | Ważona suma: `0.4 * cosine + 0.3 * ts_rank + 0.3 * recency_decay` |

### Tier 2: Post-MVP (jeśli starczy czasu)
| Heurystyka | Opis | Implementacja |
|------------|------|---------------|
| **Spreading activation** | Przywołanie node'a aktywuje sąsiadów w grafie | BFS/DFS po `edge` z malejącą wagą per hop. Sąsiedzi dołączani do wyników recall |
| **Episodic consolidation** | Grupowanie epizodów w wyższe abstrakcje | Async job: LLM podsumowuje klaster epizodów -> nowy node z edge'ami SUMMARIZES -> oryginały |
| **Co-access patterns** | Nodes często przywoływane razem stają się powiązane | Log par (node_a, node_b) w jednym recall -> po przekroczeniu progu twórz edge CO_OCCURS |
| **Contradiction detection** | Wykrywanie sprzecznych faktów w grafie | LLM porównuje nowy node z istniejącymi o podobnym embeddingu -> edge CONTRADICTS |

### Tier 3: Roadmap (post-hackathon)
| Heurystyka | Opis | Implementacja |
|------------|------|---------------|
| **Forgetting curve** | Rzadko używane wspomnienia stopniowo tracą wagę | Ebbinghaus decay: `strength = initial * e^(-t/τ)`, τ rośnie z każdym dostępem |
| **Importance scoring** | Automatyczna ocena ważności na podstawie struktury grafu | PageRank / betweenness centrality na grafie node/edge |
| **Memory reconsolidation** | Ponowna analiza starych wspomnień w świetle nowych | Gdy nowy node ma wysoki overlap z istniejącym klastrem -> LLM re-evaluates i merguje |
| **Goal-directed recall** | Recall filtrowany przez aktualny cel agenta | Agent podaje cel jako kontekst -> recall waży nodes pod kątem relevance do celu |
| **Cross-agent knowledge transfer** | Agent A uczy się z doświadczeń agenta B | Promowanie prywatnych nodes do shared graph po walidacji (propose -> approve flow) |
| **Temporal reasoning** | Wnioskowanie o sekwencjach zdarzeń | Edge'e PRECEDES/FOLLOWS + zapytania "co się stało przed/po X" z window queries |

### Wizualizacja wpływu heurystyk na recall

```
Query: "authentication issues"

Without heuristics:
  1. [node: "OAuth2 spec"] ──── cosine: 0.82
  2. [node: "JWT token format"] ── cosine: 0.79
  3. [node: "login bug #432"] ─── cosine: 0.71

With heuristics (tier 1+2):
  1. [node: "login bug #432"] ─── score: 0.91  (recency↑ + frequency↑ + cosine)
  2. [node: "auth refactor PR"] ── score: 0.85  (spreading activation from #432)
  3. [node: "OAuth2 spec"] ──── score: 0.78  (cosine high, but old + rarely accessed)
```

## Timeline (1-day hackathon)

| Phase | Duration | Activities |
|-------|----------|------------|
| Setup | 1h | Docker, deps, repo structure, agree on interfaces |
| Core Build | 4-5h | Parallel work: data layer, MCP server, ingestion |
| Integration | 2h | Wire everything together, end-to-end flow |
| Demo Polish | 1-2h | Demo scenario, fix bugs, prepare presentation |

## Tech Stack

| Component | Technology |
|-----------|------------|
| LLM | Gemini (via Pydantic AI google provider) |
| Embeddings | Gemini embedding model (768 dims) |
| Database | PostgreSQL 16 + pgvector + tsvector |
| MCP Server | Python MCP SDK (FastMCP) |
| Ingestion API | FastAPI |
| Agent Framework | Pydantic AI |
| Data Access | asyncpg |
| Containerization | Docker Compose |
| Language | Python 3.12 |

## Key Hackathon Scoring Points

1. **Production-grade architecture**: Relational graph model scales naturally with PostgreSQL, not a toy demo
2. **Standards compliance**: MCP server = standard agent protocol
3. **Knowledge graphs**: Core of the entire system, with discoverable ontology
4. **Deterministic verification**: Ontology-driven extraction reduces hallucinations
5. **Real business problem**: Agent memory is unsolved and critical for production agents
6. **Observability**: Ontology evolution, memory stats, provenance tracking
7. **Google/Gemini integration**: Embeddings + LLM extraction + Pydantic AI

## Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Schema needs iteration during hackathon | Medium | JSONB properties absorb unexpected attributes without migrations |
| LLM extraction quality poor | Medium | Use structured output (Pydantic models) + ontology constraints |
| Integration takes too long | High | Define interfaces upfront, use mock data for parallel dev |
| Demo not impressive enough | Medium | Pre-ingest rich dataset, script the demo flow |
| pgvector/tsvector setup issues | Low | Use Docker image with extensions pre-installed |

## Minimal Viable Demo (if time is tight)

If we're running behind, cut to:
1. PostgreSQL with just `node`, `edge`, `node_type`, `edge_type`, `episode`
2. MCP server with: `store_memory`, `recall`, `discover_ontology`
3. Single ingestion source (text/documents)
4. One demo agent showing recall + graph traversal

This still demonstrates the core value proposition: structured, ontology-driven, graph-based agent memory via MCP.
