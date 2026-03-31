# Stage 2: Content-Merging Upsert

**Goal**: Enhance the librarian prompt to explicitly handle cross-agent content merging in shared graphs.
**Dependencies**: Stage 1 (RLS removal — needed so cross-agent updates actually execute)

---

## Steps

### 1. Verify existing UPDATE logic is sufficient

- File: `src/neocortex/db/adapter.py`
- Lines: 706-727 (UPDATE query in `upsert_node`)
- Details:
  - Current: `content = COALESCE($1, content)` — replaces old content with new if non-NULL.
  - The librarian prompt already instructs the LLM to read existing content via
    `find_similar_nodes` (which returns the `content` field) and produce a
    "COMPREHENSIVE updated description merging old + new" (agents.py line 302-303).
  - So the LLM is expected to produce merged content BEFORE calling
    `create_or_update_node`. The DB just needs to accept it.
  - **No SQL change needed** — COALESCE is correct because the librarian passes
    the already-merged content. The content merging is an LLM-level concern,
    not a DB-level one.

### 2. Enhance librarian prompt for cross-agent awareness

- File: `src/neocortex/extraction/agents.py`
- Lines: 289-355 (system prompt for tool-driven librarian)
- Details:
  - The current prompt says "If new info ADDS knowledge: use create_or_update_node with
    a COMPREHENSIVE updated description merging old + new" (line 302-303).
  - This is correct but agents don't know they're in a shared graph context.
  - **Add** after the existing "## Rules" section (line 347, before line 354):
    ```
    ## Shared Graph Context
    You may be curating a shared knowledge graph where multiple agents contribute.
    When you find an existing node via find_similar_nodes:
    - The node may have been created by a different agent.
    - You MUST still merge your new knowledge into it — do NOT skip updates
      because the node "belongs" to someone else.
    - When merging, produce a COMPREHENSIVE description that combines the existing
      content with the new information. Never discard existing facts.
    - Include both perspectives when they differ (e.g., "Backend team reports X.
      ML team reports Y.").
    ```

### 3. Ensure `find_similar_nodes` returns full content

- File: `src/neocortex/extraction/agents.py`
- Lines: 451-550 (`find_similar_nodes` tool)
- Details:
  - Currently returns `content` field (line 504): `"content": str(node.content or "")`.
  - This is already sufficient — the librarian can read existing content before deciding
    what to write. **No code change needed** here.
  - Verify that `find_similar_nodes` works cross-agent in shared graphs: the query
    runs within the schema scope, and after Stage 1 (RLS removal), all nodes are
    visible regardless of owner.

---

## Verification

- [ ] Read `agents.py` librarian prompt and confirm "Shared Graph Context" section exists
- [ ] Verify `find_similar_nodes` returns content field (line 504)
- [ ] `uv run pytest tests/ -v -k "librarian"` — tests pass
- [ ] `uv run pytest tests/ -v` — full suite passes

---

## Commit

`feat(extraction): add cross-agent content merging awareness to librarian prompt`
