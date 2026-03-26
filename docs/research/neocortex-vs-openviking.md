# NeoCortex vs. OpenViking: Comparative Analysis

**Date**: 2026-03-27

---

## 1. What Each System Is

**NeoCortex** — An MCP server providing graph-based long-term memory for AI agents. Built on PostgreSQL (pgvector + tsvector). Agents interact via 3 natural-language tools (remember/recall/discover). Internal agent pipeline (Ontology/Extraction/Librarian) processes memories asynchronously.

[**OpenViking**](https://github.com/volcengine/OpenViking) (ByteDance/Volcengine) — A hierarchical virtual filesystem for agent context, organized under the `viking://` protocol with L0/L1/L2 tiered context loading. Ships as a Claude Code plugin. On [LoCoMo](https://github.com/snap-research/locomo) benchmark, boosted task completion from 35.65% to 52.08% while cutting token costs by 83%.

---

## 2. Architectural Philosophy

|                  | NeoCortex                                                               | OpenViking                                               |
| ---------------- | ----------------------------------------------------------------------- | -------------------------------------------------------- |
| **Mental model** | Knowledge graph (nodes + edges + ontology)                              | Virtual filesystem (hierarchical paths)                  |
| **Metaphor**     | A brain — concepts and connections                                      | A filing cabinet — folders and files                     |
| **Core insight** | Relationships between knowledge are as valuable as the knowledge itself | Progressive detail loading prevents context window bloat |

```
NeoCortex:                              OpenViking:

  [OAuth2 spec]                          viking://
       │ MENTIONS                        ├── memories/
       v                                 │   ├── oauth2-spec.md
  [JWT tokens] ──CAUSED_BY──> [Bug #432] │   ├── jwt-tokens.md
       │ PART_OF                         │   └── bug-432.md
       v                                 ├── resources/
  [Auth Module] ──CHANGED_BY──> [PR #89] │   └── auth-module/
                                         └── skills/
                                             └── debugging-auth.md
```

---

## 3. Head-to-Head Comparison

### 3.1 Knowledge Representation

| Dimension                       | NeoCortex                                                       | OpenViking                                                |
| ------------------------------- | --------------------------------------------------------------- | --------------------------------------------------------- |
| **Structure**                   | Graph — typed entities + typed relationships                    | Tree — hierarchical paths                                 |
| **Cross-cutting relationships** | Native (edges between any nodes)                                | Not possible without duplicating content across branches  |
| **Schema**                      | Evolving ontology (node_type, edge_type) discovered by LLM      | Fixed categories (memories, resources, skills)            |
| **Schema introspection**        | `discover` tool — agent can query what types of knowledge exist | Static — agent always sees the same top-level categories  |
| **Multi-hop reasoning**         | "How is A related to B?" via graph traversal                    | Requires searching all files + hoping for keyword overlap |

**Verdict**: NeoCortex wins on representational power. A graph captures relationships a tree cannot.

### 3.2 Token Efficiency

| Dimension              | NeoCortex                                                  | OpenViking                                                    |
| ---------------------- | ---------------------------------------------------------- | ------------------------------------------------------------- |
| **Context loading**    | `recall` returns full node content, ranked by hybrid score | L0/L1/L2 tiered loading — summaries first, details on demand  |
| **Token cost**         | Not optimized — no summarization layer                     | 83% reduction on LoCoMo benchmark                             |
| **Progressive detail** | Not supported                                              | Core feature — agent works with metadata until it needs depth |

**Verdict**: OpenViking wins decisively. Tiered loading is a genuinely smart design that NeoCortex lacks.

### 3.3 Agent Interface

| Dimension          | NeoCortex                                                 | OpenViking                                              |
| ------------------ | --------------------------------------------------------- | ------------------------------------------------------- |
| **Protocol**       | MCP (open standard, JSON-RPC 2.0)                         | Claude Code plugin (proprietary integration)            |
| **Compatibility**  | Any MCP-compatible agent (Claude, Gemini, GPT, custom)    | Claude Code only                                        |
| **Tool count**     | 3 (remember, recall, discover)                            | Plugin-managed (transparent to user)                    |
| **Agent coupling** | Zero — agent speaks protocol, knows nothing about backend | Tight — integrated into Claude Code's session lifecycle |

**Verdict**: NeoCortex wins on portability and standards. OpenViking wins on out-of-the-box coding agent experience.

### 3.4 Storage & Infrastructure

| Dimension       | NeoCortex                                              | OpenViking                                           |
| --------------- | ------------------------------------------------------ | ---------------------------------------------------- |
| **Database**    | PostgreSQL 16 (pgvector + tsvector + relational graph) | Likely file-based or lightweight DB (not documented) |
| **Deployment**  | Single Docker container                                | Claude Code plugin install                           |
| **Search**      | Hybrid: vector cosine + BM25 + graph traversal         | Hierarchical path navigation + likely keyword search |
| **Scalability** | PostgreSQL scales well with indexing                   | Unknown — filesystem metaphor may struggle at scale  |

**Verdict**: NeoCortex has stronger engineering foundations. OpenViking is simpler to adopt.

### 3.5 Memory Model

| Dimension               | NeoCortex                                               | OpenViking                                 |
| ----------------------- | ------------------------------------------------------- | ------------------------------------------ |
| **Episodic**            | Dedicated `episode` table (raw, append-only, per-agent) | Stored as files in `memories/`             |
| **Semantic**            | Nodes + edges in shared knowledge graph                 | Stored as files in `resources/`            |
| **Procedural**          | Not supported (gap)                                     | Stored as files in `skills/`               |
| **Personal vs. shared** | Per-agent subgraph + shared graph                       | Per-agent context (no multi-agent sharing) |
| **Temporal tracking**   | Not in MVP (gap)                                        | Unknown                                    |
| **Forgetting/decay**    | Planned (Tier 2+) but not in MVP                        | Unknown                                    |

**Verdict**: Mixed. NeoCortex has richer episodic/semantic separation but lacks procedural memory. OpenViking's skills/ category covers procedural memory by default.

### 3.6 Benchmarks

| Dimension                  | NeoCortex  | OpenViking                                  |
| -------------------------- | ---------- | ------------------------------------------- |
| **LoCoMo task completion** | Untested   | 35.65% → 52.08% (+46% relative improvement) |
| **Token cost reduction**   | Unmeasured | 83% reduction                               |
| **Other benchmarks**       | None       | None published beyond LoCoMo                |

**Verdict**: OpenViking has proof. NeoCortex has theory.

---

## 4. What NeoCortex Should Steal from OpenViking

### 4.1 Tiered Context Loading (High Priority)

The single most impactful idea. Add a `detail` parameter to `recall`:

| Level          | Returns                                         | Token cost |
| -------------- | ----------------------------------------------- | ---------- |
| `summary` (L0) | Node names + types + relevance scores           | Very low   |
| `context` (L1) | Node content summaries + key relationships      | Medium     |
| `full` (L2)    | Full node content + all edges + source episodes | High       |

Implementation sketch:

```
recall("authentication issues")                    → defaults to "context" (L1)
recall("authentication issues", detail="summary")  → just names + scores
recall("authentication issues", detail="full")     → everything
```

This could be the `recall` tool's 3rd parameter (after `query` and `limit`). Minimal API change, major token savings.

### 4.2 Procedural Memory (Medium Priority)

OpenViking's `skills/` category is simple but effective. NeoCortex should add a `Procedure` node type:

```json
{
  "type": "Procedure",
  "name": "Debug authentication failures",
  "content": "1. Check token expiry. 2. Verify JWT signature. 3. Check RBAC permissions.",
  "properties": { "trigger": "auth error", "success_rate": 0.85 }
}
```

This fills the procedural memory gap with minimal schema change (just a new row in `node_type`).

---

## 5. What OpenViking Can't Do That NeoCortex Can

1. **Relationship traversal** — "What PRs affected the auth module that also touched the user model?" requires graph queries. A filesystem would need full-text search across every file.

2. **Ontology evolution** — When NeoCortex ingests a new type of data (e.g., security audit logs), the Ontology Agent creates new node_type/edge_type automatically. OpenViking's 3-folder structure is fixed.

3. **Cross-agent memory sharing** — Two agents connected to the same NeoCortex MCP server share a knowledge graph. OpenViking is per-Claude-Code-session.

4. **Hybrid search** — Vector similarity + BM25 + graph proximity is fundamentally more powerful than hierarchical path navigation for ambiguous queries.

5. **Schema introspection** — `discover("what do I know about security?")` returns relevant ontology slices. No equivalent in OpenViking.

---

## 6. Positioning Summary

```
                    Token Efficiency
                         ^
                         |
            OpenViking   |
               *         |
                         |
     ──────────────────────────────────> Knowledge Richness
                         |
                         |            * NeoCortex
                         |              (with tiered loading
                         |               moves here: *)
                         |
```

**One-liner**: OpenViking organizes agent memory like a filesystem — it tells you where things are. NeoCortex organizes it like a brain — it tells you how things relate. The ideal system does both.

**For the hackathon pitch**: "We studied OpenViking's tiered loading approach and incorporated progressive detail levels into our recall system. But where OpenViking stops at organizing files, NeoCortex discovers the structure of knowledge itself."
