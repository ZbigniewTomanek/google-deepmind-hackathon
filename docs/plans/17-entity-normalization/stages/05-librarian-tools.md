# Stage 5: Enhanced Librarian Dedup Tools

**Goal**: Give the librarian agent better tools for finding existing entities (fuzzy search fallback) and strengthen the prompt for quantitative update propagation.

**Dependencies**: Stage 2 (fuzzy matching), Stage 4 (edge type normalization)

---

## Rationale

The librarian currently has two lookup tools:
1. `find_node_by_name(name)` — exact match, used first per prompt instructions
2. `search_existing_nodes(query)` — semantic + full-text search

The prompt directs: "Use find_node_by_name to check if it already exists". If exact match
fails, the librarian often creates a new node instead of falling back to semantic search.
This is the root cause of name variant duplication.

Additionally, Plan 16.5 found that quantitative corrections (87% → 94.2%) don't always
propagate to node content. The librarian sometimes updates the episode but leaves the
node's content field unchanged.

---

## Steps

### Step 1: Add `find_similar_nodes` tool to librarian

In `src/neocortex/extraction/agents.py`, add a new tool that combines exact lookup
with fuzzy fallback:

```python
@agent.tool
async def find_similar_nodes(
    ctx: RunContext[LibrarianAgentDeps],
    name: str,
    limit: int = 5,
) -> list[dict]:
    """Find nodes with names similar to the given name.
    Uses exact match first, then alias resolution, then fuzzy matching.
    ALWAYS use this instead of find_node_by_name when checking for existing entities.

    Args:
        name: Entity name to search for (or a variant/alias)
        limit: Max results to return (default 5)

    Returns:
        List of {name, type_name, content, importance, node_id, match_type} dicts
        where match_type is 'exact', 'alias', or 'fuzzy'
    """
    results = []
    types = await ctx.deps.repo.get_node_types(
        ctx.deps.agent_id, target_schema=ctx.deps.target_schema
    )
    type_names = {t.id: t.name for t in types}

    # 1. Exact match
    exact = await ctx.deps.repo.find_nodes_by_name(
        ctx.deps.agent_id, name, target_schema=ctx.deps.target_schema
    )
    for node in exact:
        results.append({
            "node_id": node.id,
            "name": node.name,
            "type_name": type_names.get(node.type_id, "Unknown"),
            "content": node.content,
            "importance": node.importance,
            "match_type": "exact",
        })

    if results:
        return results

    # 2. Alias resolution
    alias_node = await ctx.deps.repo.resolve_alias(
        ctx.deps.agent_id, name, target_schema=ctx.deps.target_schema
    )
    if alias_node:
        results.append({
            "node_id": alias_node.id,
            "name": alias_node.name,
            "type_name": type_names.get(alias_node.type_id, "Unknown"),
            "content": alias_node.content,
            "importance": alias_node.importance,
            "match_type": "alias",
        })
        return results

    # 3. Fuzzy matching
    fuzzy = await ctx.deps.repo.find_nodes_fuzzy(
        ctx.deps.agent_id, name, threshold=0.3,
        limit=limit, target_schema=ctx.deps.target_schema,
    )
    for node, score in fuzzy:
        results.append({
            "node_id": node.id,
            "name": node.name,
            "type_name": type_names.get(node.type_id, "Unknown"),
            "content": node.content,
            "importance": node.importance,
            "match_type": "fuzzy",
            "similarity": round(score, 3),
        })

    # 4. Semantic search fallback
    if not results and ctx.deps.embeddings:
        embedding = await ctx.deps.embeddings.embed(name)
        semantic = await ctx.deps.repo.search_nodes(
            ctx.deps.agent_id, name, limit=limit,
            query_embedding=embedding,
        )
        for node, score in semantic:
            if score > 0.5:  # only high-confidence semantic matches
                results.append({
                    "node_id": node.id,
                    "name": node.name,
                    "type_name": type_names.get(node.type_id, "Unknown"),
                    "content": node.content,
                    "importance": node.importance,
                    "match_type": "semantic",
                    "similarity": round(score, 3),
                })

    return results
```

### Step 2: Update librarian system prompt

Replace the current workflow instructions with enhanced dedup guidance:

```python
"## Workflow",
"For each extracted entity:",
"  1. Use find_similar_nodes to check if it already exists.",
"     This checks exact name, aliases, fuzzy matches, and semantic similarity.",
"  2. If a match is found (any match_type): compare the extracted description",
"     with the existing content.",
"     - If new info ADDS knowledge: use create_or_update_node with a",
"       COMPREHENSIVE updated description merging old + new.",
"     - If new info includes QUANTITATIVE UPDATES (numbers, percentages,",
"       dates, versions): ALWAYS update the node content to reflect the",
"       new values. Include both old and new values with context",
"       (e.g., 'precision improved from 87% to 94.2%').",
"     - If new info CONTRADICTS existing: update with correct info and",
"       note the contradiction in properties.",
"  3. If no match is found: use create_or_update_node to create it.",
"  4. When creating a new node with a name that has known variants",
"     (e.g., 'Apache Kafka' when 'Kafka' might be used later),",
"     mention the variants in the node content.",
"",
"For each extracted relation:",
"  1. Use get_edges_between to check for existing relationships",
"  2. If an edge exists with a similar meaning (even different type name),",
"     keep it — do NOT create a duplicate.",
"  3. If an edge is now WRONG, use remove_edge and create the correct one.",
"  4. If no relevant edge exists, use create_or_update_edge.",
"",
"## Quantitative Update Rules",
"When an extracted entity contains updated numbers, percentages, dates,",
"or version strings, you MUST update the node content to reflect the new",
"values. This is non-negotiable. Examples:",
"- 'precision: 87%' → 'precision: 94.2%' → node content MUST say '94.2%'",
"- 'launch: June' → 'launch: August 1' → node content MUST say 'August 1'",
"- 'v2.3' → 'v3.0' → node content MUST say 'v3.0'",
```

### Step 3: Deprecate `find_node_by_name` (soft)

Keep `find_node_by_name` available (backward compat) but add a docstring note:

```python
"""Look up a specific node by exact name (case-insensitive).

DEPRECATED: Prefer find_similar_nodes which also checks aliases and
fuzzy matches. Use this only when you need strict exact-match semantics.
"""
```

### Step 4: Add alias registration to `create_or_update_node` tool

When the librarian creates or updates a node, automatically register aliases
from canonicalization:

```python
@agent.tool
async def create_or_update_node(
    ctx: RunContext[LibrarianAgentDeps],
    name: str,
    type_name: str,
    content: str,
    properties: dict | None = None,
    importance: float = 0.5,
) -> dict:
    """..."""
    from neocortex.normalization import canonicalize_name

    canonical, aliases = canonicalize_name(name)
    # Use canonical name for the node
    name = canonical

    # ... existing create/update logic ...

    # After successful upsert, register aliases
    for alias in aliases:
        await ctx.deps.repo.register_alias(
            ctx.deps.agent_id, node.id, alias,
            source="librarian", target_schema=ctx.deps.target_schema,
        )

    return result
```

### Step 5: Tests

Add to `tests/mcp/test_fuzzy_dedup.py`:

```python
# Test: find_similar_nodes returns match_type correctly
# Test: find_similar_nodes falls through exact → alias → fuzzy → semantic
# Test: librarian prompt includes quantitative update rules
# Test: create_or_update_node registers aliases from canonicalization
# Test: deprecated find_node_by_name still works
```

---

## Verification

```bash
# Run all tests
uv run pytest tests/ -v --timeout=60

# Verify the new tool is registered on the librarian agent
python -c "
from neocortex.extraction.agents import build_librarian_agent
agent = build_librarian_agent(use_tools=True)
tool_names = [t.name for t in agent._tools]
assert 'find_similar_nodes' in tool_names, f'Missing tool. Available: {tool_names}'
print(f'Librarian tools: {tool_names}')
"
```

Check:
- [ ] `find_similar_nodes` tool registered on librarian agent
- [ ] Tool returns correct `match_type` for each lookup method
- [ ] Quantitative update rules in system prompt
- [ ] `create_or_update_node` auto-registers canonicalization aliases
- [ ] `find_node_by_name` still works (backward compat)
- [ ] All tests pass

---

## Commit

```
feat(librarian): add find_similar_nodes tool with fuzzy/alias fallback

Replaces find_node_by_name as the primary lookup in librarian workflow.
Chains: exact → alias → trigram → semantic search.
Strengthens prompt for quantitative update propagation.
Auto-registers canonicalization aliases on node creation.
```
