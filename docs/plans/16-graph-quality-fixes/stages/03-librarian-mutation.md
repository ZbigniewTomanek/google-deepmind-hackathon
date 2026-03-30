# Stage 3: Librarian Mutation Tools & Pipeline Redesign

**Goal**: Give the librarian agent tools to directly curate the knowledge graph, replacing the blind `_persist_payload()` with intelligent, tool-driven persistence.

**Dependencies**: Stage 2 (librarian has retrieval tools and repo access)

**Priority**: P0 — The core architectural change

---

## Why This Stage Exists

Currently, the librarian produces a `LibrarianPayload` (list of entities + relations),
and `_persist_payload()` blindly UPSERTs them. The librarian cannot:
- Update a node's content to reflect new information
- Merge two duplicate nodes into one
- Archive a stale node or edge
- Choose to keep an existing edge type instead of the extractor's new one
- Create a CONTRADICTS or SUPERSEDES edge

With mutation tools, the librarian becomes a **decision-making curator**:
it sees the current graph (Stage 2 tools), reasons about what should change,
and executes those changes directly.

---

## Steps

### 3.1 Add mutation tools to the librarian agent

**File**: `src/neocortex/extraction/agents.py`

Add inside `build_librarian_agent()`, after the retrieval tools from Stage 2:

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
        """Create a new node or update an existing one.
        Searches by name first — if a node with this name exists,
        updates its content and merges properties. If not, creates new.

        ALWAYS provide a content description, even for existing nodes.
        The content should be a comprehensive, up-to-date summary.

        Args:
            name: Canonical entity name
            type_name: Node type (must be from available types)
            content: Description of the entity (REQUIRED — always provide this)
            properties: Optional key-value properties
            importance: 0.0-1.0 importance score

        Returns:
            Dict with node_id, name, type_name, is_new, action taken
        """
        node_type = await ctx.deps.repo.get_or_create_node_type(
            ctx.deps.agent_id, type_name,
            target_schema=ctx.deps.target_schema,
        )
        # Compute embedding for the content
        embedding = None
        if ctx.deps.embeddings and content:
            embedding = await ctx.deps.embeddings.embed(content)

        # Get episode_id from the pipeline context for source tracking
        episode_id = ctx.deps.properties.get("episode_id") if hasattr(ctx.deps, 'properties') else None
        props = {**(properties or {})}
        if episode_id:
            props["_source_episode"] = episode_id

        node = await ctx.deps.repo.upsert_node(
            agent_id=ctx.deps.agent_id,
            name=name,
            type_id=node_type.id,
            content=content,
            properties=props,
            embedding=embedding,
            target_schema=ctx.deps.target_schema,
            importance=importance,
        )
        is_new = (node.created_at == node.updated_at)  # approximate
        return {
            "node_id": node.id,
            "name": node.name,
            "type_name": type_name,
            "is_new": is_new,
            "action": "created" if is_new else "updated",
        }

    @agent.tool
    async def create_or_update_edge(
        ctx: RunContext[LibrarianAgentDeps],
        source_name: str,
        target_name: str,
        edge_type: str,
        weight: float = 1.0,
        properties: dict | None = None,
    ) -> dict:
        """Create a new edge or update an existing one between two nodes.
        Both nodes must already exist (create them first with create_or_update_node).

        Before calling this, use get_edges_between to check for existing relationships.
        If an edge already exists with a suitable type, prefer updating it over creating
        a new one with a different type.

        Args:
            source_name: Name of the source node (must exist)
            target_name: Name of the target node (must exist)
            edge_type: Relationship type (e.g., MEMBER_OF, WORKS_ON)
            weight: Edge weight 0.0-1.0 (default 1.0)
            properties: Optional properties (evidence text, etc.)

        Returns:
            Dict with edge_id, source, target, type, action
        """
        # Resolve node IDs by name
        src_nodes = await ctx.deps.repo.find_nodes_by_name(
            ctx.deps.agent_id, source_name,
            target_schema=ctx.deps.target_schema,
        )
        tgt_nodes = await ctx.deps.repo.find_nodes_by_name(
            ctx.deps.agent_id, target_name,
            target_schema=ctx.deps.target_schema,
        )
        if not src_nodes:
            return {"error": f"Source node '{source_name}' not found. Create it first."}
        if not tgt_nodes:
            return {"error": f"Target node '{target_name}' not found. Create it first."}

        et = await ctx.deps.repo.get_or_create_edge_type(
            ctx.deps.agent_id, edge_type,
            target_schema=ctx.deps.target_schema,
        )

        episode_id = ctx.deps.properties.get("episode_id") if hasattr(ctx.deps, 'properties') else None
        props = {**(properties or {})}
        if episode_id:
            props["_source_episode"] = episode_id

        edge = await ctx.deps.repo.upsert_edge(
            agent_id=ctx.deps.agent_id,
            source_id=src_nodes[0].id,
            target_id=tgt_nodes[0].id,
            type_id=et.id,
            weight=weight,
            properties=props,
            target_schema=ctx.deps.target_schema,
        )
        return {
            "edge_id": edge.id,
            "source": source_name,
            "target": target_name,
            "type": edge_type,
            "action": "upserted",
        }

    @agent.tool
    async def archive_node(
        ctx: RunContext[LibrarianAgentDeps],
        node_id: int,
        reason: str,
    ) -> dict:
        """Soft-delete a node that is no longer current.
        Use this when new information supersedes or contradicts an existing node.
        The node is not hard-deleted — it's marked as forgotten and excluded from future recall.

        Args:
            node_id: ID of the node to archive (from find_node_by_name results)
            reason: Why this node is being archived

        Returns:
            Dict confirming the archival
        """
        count = await ctx.deps.repo.mark_forgotten(
            ctx.deps.agent_id, [node_id],
        )
        return {
            "archived": count > 0,
            "node_id": node_id,
            "reason": reason,
        }

    @agent.tool
    async def remove_edge(
        ctx: RunContext[LibrarianAgentDeps],
        edge_id: int,
        reason: str,
    ) -> dict:
        """Remove a stale or incorrect edge from the graph.
        Use this when a relationship is no longer valid (e.g., Alice is no longer
        on the billing team, so the MEMBER_OF→Billing edge should be removed).

        Args:
            edge_id: ID of the edge to remove (from get_edges_between or inspect results)
            reason: Why this edge is being removed

        Returns:
            Dict confirming the removal
        """
        # Need to add delete_edge to protocol or use graph_service
        # For now, we can archive via weight=0 as a soft delete
        # TODO: Add proper edge deletion to protocol in this stage
        # Temporary: set weight to 0 to effectively disable
        await ctx.deps.repo.reinforce_edges(
            ctx.deps.agent_id,
            [edge_id],
            delta=-10.0,  # Drop to floor
            ceiling=0.0,
        )
        return {
            "removed": True,
            "edge_id": edge_id,
            "reason": reason,
        }
```

**Note on `remove_edge`**: The MemoryRepository protocol doesn't have an edge
deletion method. Options:
- **Option A**: Add `delete_edge(agent_id, edge_id)` to the protocol and implement
  in adapter/mock. This is clean but requires protocol extension.
- **Option B**: Set weight to 0 (soft delete via weight floor). Less clean but works
  without protocol changes.

Prefer Option A — add `delete_edge` to the protocol.

### 3.2 Add `delete_edge` to the protocol

**File**: `src/neocortex/db/protocol.py`

```python
async def delete_edge(
    self, agent_id: str, edge_id: int,
    target_schema: str | None = None,
) -> bool:
    """Hard-delete an edge by ID. Returns True if deleted."""
```

**File**: `src/neocortex/db/adapter.py`

```python
async def delete_edge(self, agent_id, edge_id, target_schema=None):
    schema_name = await self._resolve_schema(agent_id, target_schema)
    async with self._scoped_conn(schema_name, agent_id, target_schema) as conn:
        result = await conn.execute(
            "DELETE FROM edge WHERE id = $1", edge_id,
        )
    return result == "DELETE 1"
```

**File**: `src/neocortex/db/mock.py` — equivalent in-memory deletion.

Then update `remove_edge` tool to use `repo.delete_edge()`.

### 3.3 Add episode_id to LibrarianAgentDeps

**File**: `src/neocortex/extraction/agents.py`

```python
@dataclass
class LibrarianAgentDeps:
    episode_text: str
    node_types: list[str]
    edge_types: list[str]
    extracted_entities: list[ExtractedEntity]
    extracted_relations: list[ExtractedRelation]
    repo: "MemoryRepository"
    embeddings: "EmbeddingService | None"
    agent_id: str
    target_schema: str | None = None
    episode_id: int | None = None              # NEW: for source tracking in tools
```

Tools use `ctx.deps.episode_id` directly instead of the `properties` hack.

### 3.4 Redesign librarian output model

**File**: `src/neocortex/extraction/schemas.py`

The librarian's output changes from "entities to persist" to "summary of what was done":

```python
class CurationAction(BaseModel):
    """A single action taken by the librarian during graph curation."""
    action: str  # "created_node", "updated_node", "archived_node", "created_edge", "removed_edge"
    entity_name: str | None = None
    edge_source: str | None = None
    edge_target: str | None = None
    details: str = ""

class CurationSummary(BaseModel):
    """Summary of all curation actions taken by the librarian.

    This replaces LibrarianPayload — the librarian now executes changes
    via tools and reports what it did, rather than producing a payload
    for blind persistence.
    """
    actions: list[CurationAction] = Field(default_factory=list)
    summary: str = ""
    entities_created: int = 0
    entities_updated: int = 0
    entities_archived: int = 0
    edges_created: int = 0
    edges_removed: int = 0
```

Update the agent's `output_type`:
```python
agent = Agent(
    model,
    output_type=CurationSummary,  # was: LibrarianPayload
    deps_type=LibrarianAgentDeps,
    ...
)
```

### 3.5 Update the librarian system prompt for curation workflow

**File**: `src/neocortex/extraction/agents.py`

```python
system_prompt=(
    "You are a knowledge graph curator. You receive extracted entities and relations "
    "from a text, and your job is to integrate them into the existing knowledge graph "
    "using the tools available to you.",
    "",
    "## Workflow",
    "For each extracted entity:",
    "  1. Use find_node_by_name to check if it already exists",
    "  2. If it exists: compare the extracted description with the existing content. "
    "     If the new info adds or updates knowledge, use create_or_update_node with "
    "     a COMPREHENSIVE updated description that merges old and new information.",
    "  3. If it doesn't exist: use create_or_update_node to create it.",
    "  4. If the extracted info CONTRADICTS an existing node, update the node with "
    "     correct information and note the contradiction in properties.",
    "",
    "For each extracted relation:",
    "  1. Use get_edges_between to check for existing relationships between the two nodes",
    "  2. If an edge exists with a similar meaning (even different type name), keep it — "
    "     do NOT create a duplicate with a slightly different type name.",
    "  3. If an edge exists that is now WRONG (e.g., Alice MEMBER_OF Billing, but she "
    "     moved to Auth), use remove_edge on the stale edge and create the correct one.",
    "  4. If no relevant edge exists, use create_or_update_edge.",
    "",
    "## Rules",
    "- ALWAYS provide comprehensive content when creating/updating nodes.",
    "- ALWAYS check for existing entities before creating new ones.",
    "- Prefer updating existing nodes over creating duplicates.",
    "- Normalize names to canonical form (proper casing, full names).",
    "- When in doubt about type assignment, match the existing node's type.",
    "",
    "After all curation actions, return a CurationSummary describing what you did.",
)
```

### 3.6 Rewire the pipeline to use tool-driven persistence

**File**: `src/neocortex/extraction/pipeline.py`

The critical change: `_persist_payload()` is no longer called after the librarian.
The librarian's tools already persisted everything.

```python
async def run_extraction_pipeline(repo, embeddings, agent_id, episode_id, text, ...):
    # ... phases 1-2 (ontology + extractor) unchanged ...

    # Phase 3: Librarian with tools — curates the graph directly
    librarian_result = await librarian_agent.run(
        "Integrate the extracted entities and relations into the knowledge graph.",
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
            episode_id=episode_id,
        ),
        model_settings=lib_cfg.model_settings,
    )

    # Mark episode as consolidated
    await repo.mark_episode_consolidated(agent_id, episode_id)

    # Log the curation summary
    summary = librarian_result.output
    logger.bind(action_log=True).info(
        "curation_complete",
        episode_id=episode_id,
        agent_id=agent_id,
        created=summary.entities_created,
        updated=summary.entities_updated,
        archived=summary.entities_archived,
        edges_created=summary.edges_created,
        edges_removed=summary.edges_removed,
        summary=summary.summary,
    )

    # NOTE: _persist_payload() is NO LONGER CALLED
    # The librarian's tools handled all persistence
```

### 3.7 Keep `_persist_payload` as a fallback

Don't delete `_persist_payload` yet — keep it as a fallback for:
- Non-tool agents (if someone runs with a model that doesn't support tools)
- Testing without tool execution
- Backward compatibility during migration

Add a settings flag:
```python
# In MCPSettings:
librarian_use_tools: bool = True  # False falls back to _persist_payload
```

### 3.8 Add structured logging for tool calls

Each tool should log its action to the audit trail:

```python
logger.bind(action_log=True).info(
    "librarian_tool_call",
    tool="create_or_update_node",
    node_name=name,
    action="created" if is_new else "updated",
    agent_id=ctx.deps.agent_id,
)
```

### 3.9 Add tests

- Test mutation tools against mock repo (create node, update node, archive, edges)
- Test full pipeline flow: remember → extract → librarian with tools → verify graph state
- Test fallback to `_persist_payload` when `librarian_use_tools=False`
- Test CurationSummary output matches actual changes made

---

## Verification

```bash
# Run mutation tool tests
uv run pytest tests/ -v -k "librarian_mutation or curation"

# Integration test: full pipeline with tools
uv run pytest tests/ -v -k "extraction_pipeline"

# Verify tools work with mock DB
NEOCORTEX_MOCK_DB=true uv run python -c "
from neocortex.extraction.agents import build_librarian_agent
a = build_librarian_agent()
tools = [t.name for t in a._function_tools.values()]
print('All tools:', tools)
assert 'create_or_update_node' in tools
assert 'create_or_update_edge' in tools
assert 'archive_node' in tools
assert 'remove_edge' in tools
print('OK')
"

# Full suite
uv run pytest tests/ -v
```

- [ ] 4 mutation tools registered: create_or_update_node, create_or_update_edge, archive_node, remove_edge
- [ ] `delete_edge` added to protocol and both implementations
- [ ] Pipeline no longer calls `_persist_payload` by default
- [ ] CurationSummary output model works
- [ ] Fallback to `_persist_payload` works when `librarian_use_tools=False`
- [ ] Structured logging for all tool calls
- [ ] Existing tests pass

---

## Commit

```
feat(extraction): librarian mutation tools + tool-driven graph curation

Librarian agent now curates the knowledge graph directly via PydanticAI tools:
create_or_update_node, create_or_update_edge, archive_node, remove_edge.
Replaces _persist_payload() blind UPSERT with intelligent, tool-driven
persistence. The librarian searches for existing entities, decides whether
to add/update/archive, and executes changes directly.

Adds delete_edge to MemoryRepository protocol. Introduces CurationSummary
output model replacing LibrarianPayload for tool-equipped mode.

Closes: Plan 15 Issues 1, 2, 3, 5
```
