# NeoCortex

MCP server providing structured long-term memory for AI agents. Knowledge graph on PostgreSQL with semantic search (pgvector), full-text search (tsvector/BM25), and graph traversal — all behind 3 simple MCP tools.

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

## MCP Tools

Agent widzi 3 toole. Nie operuje na grafie bezpośrednio.

| Tool | Opis |
|------|------|
| `remember` | "Zapamiętaj to." Treść w języku naturalnym -> epizod + asynchroniczna ekstrakcja faktów do grafu |
| `recall` | "Co wiesz o X?" Hybrid search (semantic + lexical + graph) -> ranked wyniki z provenance |
| `discover` | "Jakie rodzaje wiedzy masz?" Zwraca ontologię, typy bytów, relacje, statystyki |

Za ekstrakcję faktów i ewolucję ontologii odpowiadają wewnętrzni agenci (Ontology Agent, Extraction Agent, Librarian Agent).

## Tech Stack

| Component | Technology |
|-----------|------------|
| LLM | Gemini (via Pydantic AI) |
| Embeddings | Gemini embedding model |
| Database | PostgreSQL 16 + pgvector + tsvector |
| MCP Server | FastMCP (Python) |
| Ingestion API | FastAPI |
| Agent Framework | Pydantic AI |
| Language | Python 3.12 |

## Project Structure

```
docs/
  plans/          # hackathon plan
  research/       # research notes on agent memory systems
src/
  pydantic_agents_playground/   # POC: 3-agent pipeline (ontology + extraction + librarian)
```

## POC: Pydantic AI Playground

Proof of concept w `src/pydantic_agents_playground`. Pipeline 3 agentów przetwarzających wiadomości: ontology proposal -> fact extraction -> normalization + SQLite persistence.

```bash
# Offline test (TestModel, bez klucza API)
uv run python -m pydantic_agents_playground --use-test-model --reset-db --run-demo

# Live z Gemini
export GOOGLE_API_KEY=your_key
uv run python -m pydantic_agents_playground --reset-db --run-demo
```

## Verification

```bash
uv run ruff check src
uv run black --check src
uv run python -m pydantic_agents_playground --use-test-model --reset-db --run-demo
```

## Docs

- [Hackathon Plan](docs/plans/01-high-levelhackathon-plan.md) — architektura, data model, memory types, heuristics roadmap
- [Agent Memory Research](docs/research/01-agent-memory-research.md)
- [Memory Systems Research](docs/research/02-memory-systems-research.md)
