# Stage 2: Librarian Retrieval Tools

**Goal**: Give the librarian agent read-only tools to query the knowledge graph during extraction, replacing unbounded context injection with on-demand retrieval.

**Dependencies**: Stage 1 (content update fix should be in place)

**Priority**: P0 — Foundation for Stage 3

---

## Why This Stage Exists

The current librarian agent receives a **flat list of all node names** pre-loaded into
its prompt (`pipeline.py:124`). This is:

1. **Unbounded** — breaks at ~50K nodes (exceeds LLM context window)
2. **Context-free** — names only, no types, no content, no relationships
3. **All-or-nothing** — can't drill into specific entities or subgraphs

With PydanticAI `@agent.tool` decorators, the librarian can **search the graph on
demand** — retrieving only the entities and subgraphs relevant to the current episode.
This scales to any graph size and gives the librarian the context it needs for
intelligent dedup and curation decisions.

---

## Steps

### 2.1 Add repository access to LibrarianAgentDeps

**File**: `src/neocortex/extraction/agents.py`
**Lines**: 193-200

Extend the deps to include graph access:

```python
@dataclass
class LibrarianAgentDeps:
    episode_text: str
    node_types: list[str]                          # keep: needed for type validation
    edge_types: list[str]                          # keep: needed for type validation
    extracted_entities: list[ExtractedEntity]       # keep: input from extractor
    extracted_relations: list[ExtractedRelation]    # keep: input from extractor
    # REMOVED: known_node_names: list[str]         # replaced by search tools
    # NEW: graph access for tools
    repo: "MemoryRepository"
    embeddings: "EmbeddingService | None"
    agent_id: str
    target_schema: str | None = None
```

Use `from __future__ import annotations` or string literal types to avoid circular
imports between agents.py and protocol.py.

### 2.2 Add type descriptions to ontology/extractor agent context

**Files**: `src/neocortex/extraction/agents.py` (ontology + extractor deps)
**File**: `src/neocortex/extraction/pipeline.py` (pass descriptions)

Extend `OntologyAgentDeps` and `ExtractorAgentDeps` to include type descriptions
(not just names). This is a lighter change — no tools needed for these agents,
just richer static context:

```python
@dataclass
class OntologyAgentDeps:
    episode_text: str
    existing_node_types: list[str]
    existing_edge_types: list[str]
    node_type_descriptions: dict[str, str]    # NEW: {type_name: description}
    edge_type_descriptions: dict[str, str]    # NEW
    domain_hint: str | None = None
```

Update `inject_context` to format types with descriptions:
```
Existing node types:
- Person: A human individual
- Algorithm: A computational method or procedure
```

In `pipeline.py`, build description dicts from `TypeInfo` objects:
```python
node_type_descs = {t.name: (t.description or "") for t in node_types}
edge_type_descs = {t.name: (t.description or "") for t in edge_types}
```

### 2.3 Register read-only PydanticAI tools on the librarian agent

**File**: `src/neocortex/extraction/agents.py`

Add tools inside `build_librarian_agent()` after creating the Agent:

```python
def build_librarian_agent(config=None):
    agent = Agent(model, output_type=LibrarianPayload, deps_type=LibrarianAgentDeps, ...)

    @agent.tool
    async def search_existing_nodes(
        ctx: RunContext[LibrarianAgentDeps],
        query: str,
        limit: int = 5,
    ) -> list[dict]:
        """Search the knowledge graph for nodes matching a query.
        Use this to check if an entity already exists before deciding
        to create a new node or update an existing one.

        Args:
            query: Search text (entity name, description fragment, etc.)
            limit: Max results to return (default 5)

        Returns:
            List of {name, type_name, content, importance, node_id} dicts
        """
        embedding = None
        if ctx.deps.embeddings:
            embedding = await ctx.deps.embeddings.embed(query)
        results = await ctx.deps.repo.search_nodes(
            ctx.deps.agent_id, query, limit=limit,
            query_embedding=embedding,
        )
        type_names = {}  # cache type_id → name lookups
        out = []
        for node, score in results:
            if node.type_id not in type_names:
                types = await ctx.deps.repo.get_node_types(
                    ctx.deps.agent_id, target_schema=ctx.deps.target_schema
                )
                type_names = {t.id: t.name for t in types}
            out.append({
                "node_id": node.id,
                "name": node.name,
                "type_name": type_names.get(node.type_id, "Unknown"),
                "content": node.content,
                "importance": node.importance,
                "relevance_score": round(score, 3),
            })
        return out

    @agent.tool
    async def find_node_by_name(
        ctx: RunContext[LibrarianAgentDeps],
        name: str,
    ) -> list[dict]:
        """Look up a specific node by exact name (case-insensitive).
        Use this to check whether a specific entity already exists and
        what type and content it has.

        Args:
            name: Entity name to look up

        Returns:
            List of matching nodes (usually 0 or 1). Multiple means duplicates exist.
        """
        nodes = await ctx.deps.repo.find_nodes_by_name(
            ctx.deps.agent_id, name, target_schema=ctx.deps.target_schema,
        )
        types = await ctx.deps.repo.get_node_types(
            ctx.deps.agent_id, target_schema=ctx.deps.target_schema
        )
        type_map = {t.id: t.name for t in types}
        return [
            {
                "node_id": n.id,
                "name": n.name,
                "type_name": type_map.get(n.type_id, "Unknown"),
                "content": n.content,
                "importance": n.importance,
                "properties": n.properties,
            }
            for n in nodes if not n.forgotten
        ]

    @agent.tool
    async def inspect_node_neighborhood(
        ctx: RunContext[LibrarianAgentDeps],
        node_id: int,
        depth: int = 1,
    ) -> dict:
        """Inspect a node and its immediate neighborhood (connected nodes and edges).
        Use this after finding a node to understand its relationships before
        deciding how to update the graph.

        Args:
            node_id: The node ID (from search or find results)
            depth: How many hops to traverse (1 = immediate neighbors, 2 = 2-hop)

        Returns:
            Dict with center node info and list of connected edges and neighbors.
        """
        neighborhood = await ctx.deps.repo.get_node_neighborhood(
            agent_id=ctx.deps.agent_id, node_id=node_id, depth=min(depth, 2),
        )
        types = await ctx.deps.repo.get_node_types(
            ctx.deps.agent_id, target_schema=ctx.deps.target_schema
        )
        edge_types = await ctx.deps.repo.get_edge_types(
            ctx.deps.agent_id, target_schema=ctx.deps.target_schema
        )
        nt_map = {t.id: t.name for t in types}
        et_map = {t.id: t.name for t in edge_types}

        edges_out = []
        neighbors_out = []
        for entry in neighborhood:
            node = entry["node"]
            neighbors_out.append({
                "node_id": node.id,
                "name": node.name,
                "type": nt_map.get(node.type_id, "Unknown"),
                "content": node.content[:100] if node.content else None,
            })
            for edge in entry["edges"]:
                edges_out.append({
                    "edge_id": edge.id,
                    "source_id": edge.source_id,
                    "target_id": edge.target_id,
                    "type": et_map.get(edge.type_id, "Unknown"),
                    "weight": edge.weight,
                })
        return {"neighbors": neighbors_out, "edges": edges_out}

    @agent.tool
    async def get_edges_between(
        ctx: RunContext[LibrarianAgentDeps],
        source_name: str,
        target_name: str,
    ) -> list[dict]:
        """Find all edges between two named nodes.
        Use this before creating an edge to check if a relationship already exists.

        Args:
            source_name: Name of the source node
            target_name: Name of the target node

        Returns:
            List of existing edges between these nodes, with type and weight.
        """
        src_nodes = await ctx.deps.repo.find_nodes_by_name(
            ctx.deps.agent_id, source_name, target_schema=ctx.deps.target_schema,
        )
        tgt_nodes = await ctx.deps.repo.find_nodes_by_name(
            ctx.deps.agent_id, target_name, target_schema=ctx.deps.target_schema,
        )
        if not src_nodes or not tgt_nodes:
            return []

        edge_types = await ctx.deps.repo.get_edge_types(
            ctx.deps.agent_id, target_schema=ctx.deps.target_schema
        )
        et_map = {t.id: t.name for t in edge_types}

        # Get neighborhood and filter for edges to target
        src = src_nodes[0]
        tgt_ids = {n.id for n in tgt_nodes}
        neighborhood = await ctx.deps.repo.get_node_neighborhood(
            agent_id=ctx.deps.agent_id, node_id=src.id, depth=1,
        )
        result = []
        for entry in neighborhood:
            for edge in entry["edges"]:
                if edge.target_id in tgt_ids or edge.source_id in tgt_ids:
                    result.append({
                        "edge_id": edge.id,
                        "source_id": edge.source_id,
                        "target_id": edge.target_id,
                        "type": et_map.get(edge.type_id, "Unknown"),
                        "weight": edge.weight,
                        "properties": edge.properties,
                    })
        return result

    return agent
```

### 2.4 Update pipeline to pass repo to librarian

**File**: `src/neocortex/extraction/pipeline.py`
**Lines**: 123-136

Replace the unbounded name list with repo injection:

```python
# BEFORE (unbounded, breaks at scale):
# known_names = await repo.list_all_node_names(agent_id, target_schema=target_schema)

# AFTER (librarian uses tools to search on demand):
librarian_result = await librarian_agent.run(
    "Normalize and deduplicate the extracted data.",
    deps=LibrarianAgentDeps(
        episode_text=text,
        node_types=[t.name for t in node_types],
        edge_types=[t.name for t in edge_types],
        extracted_entities=extraction_result.output.entities,
        extracted_relations=extraction_result.output.relations,
        repo=repo,
        embeddings=embeddings,
        agent_id=agent_id,
        target_schema=target_schema,
    ),
    model_settings=lib_cfg.model_settings,
)
```

### 2.5 Update librarian system prompt

**File**: `src/neocortex/extraction/agents.py`
**Lines**: 212-221

Update the system prompt to reflect the new capability:

```python
system_prompt=(
    "You are a knowledge graph librarian with access to the existing graph. "
    "Your job is to integrate new extracted knowledge into the graph intelligently.",
    "Before creating or updating entities, use your tools to check what already exists.",
    "For each extracted entity:",
    "  1. Use find_node_by_name or search_existing_nodes to check if it exists",
    "  2. If it exists, inspect its current state and decide: update content? keep as-is?",
    "  3. If it's new, verify the type assignment against existing types",
    "For each extracted relation:",
    "  1. Use get_edges_between to check for existing relationships",
    "  2. If an edge exists with a different type, prefer the existing type unless the new type is clearly more accurate",
    "Normalize entity names to canonical forms.",
    "Preserve importance scores from extractor (max semantics if merging).",
)
```

### 2.6 Update librarian inject_context

The `inject_context` no longer needs to include the full known names list.
It should still show extracted entities/relations and available types:

```python
@agent.instructions
async def inject_context(ctx: RunContext[LibrarianAgentDeps]) -> str:
    entities_str = "\n".join(
        f"- {e.name} [{e.type_name}]: {e.description or 'no desc'}"
        for e in ctx.deps.extracted_entities
    ) or "- none"
    relations_str = "\n".join(
        f"- {r.source_name} --[{r.relation_type}]--> {r.target_name}"
        for r in ctx.deps.extracted_relations
    ) or "- none"
    return "\n".join([
        "Source text:", ctx.deps.episode_text, "",
        "Available node types:",
        "\n".join(f"- {n}" for n in ctx.deps.node_types) or "- none", "",
        "Available edge types:",
        "\n".join(f"- {n}" for n in ctx.deps.edge_types) or "- none", "",
        "Extracted entities (from extractor — your job is to curate these):",
        entities_str, "",
        "Extracted relations:",
        relations_str, "",
        "IMPORTANT: Use your tools to check the existing graph before making decisions.",
        "Do NOT assume entities are new — always verify with find_node_by_name first.",
    ])
```

### 2.7 Add tests

- Test that tools return correct results against mock repo
- Test that librarian agent is built with tools registered
- Test that pipeline passes repo to librarian deps
- Test that `list_all_node_names` is no longer called in the extraction path

---

## Verification

```bash
# Verify tools are registered
uv run python -c "
from neocortex.extraction.agents import build_librarian_agent
a = build_librarian_agent()
print('Tools:', [t.name for t in a._function_tools.values()])
"

# Run tests
uv run pytest tests/ -v -k "librarian"

# Full suite
uv run pytest tests/ -v
```

- [ ] Librarian agent has 4 tools: search_existing_nodes, find_node_by_name, inspect_node_neighborhood, get_edges_between
- [ ] Tools return correct data from mock repo
- [ ] Pipeline no longer calls `list_all_node_names` in extraction path
- [ ] Ontology/extractor agents receive type descriptions
- [ ] Existing tests pass

---

## Commit

```
feat(extraction): add graph retrieval tools to librarian agent

Librarian now has PydanticAI @agent.tool decorators for on-demand graph
querying: search_existing_nodes, find_node_by_name, inspect_node_neighborhood,
get_edges_between. Replaces unbounded list_all_node_names context injection
(which broke at ~50K nodes) with scalable tool-based retrieval.

Refs: Plan 15 Issues 3, 5, 6
```
