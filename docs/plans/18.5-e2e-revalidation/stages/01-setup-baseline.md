# Stage 1: Setup & Baseline

**Goal**: Verify MCP tools are functional and record the baseline graph state before ingesting any test episodes.
**Dependencies**: None

---

## Steps

1. **Verify MCP connectivity**
   - Call `discover_graphs` to list all available graphs
   - Confirm the tool returns successfully (even if no graphs exist yet)
   - Record the response -- note any pre-existing graphs and their sizes

2. **Record baseline state**
   - If a personal graph already exists for the current agent, note its current size:
     - Node count
     - Edge count
     - Episode count
   - If no graph exists, record "empty baseline"
   - Save these numbers -- they'll be subtracted from final counts to isolate test data

3. **Verify source repo accessibility**
   - Confirm the datawalk-entity-resolution repo exists at:
     `/Users/zbigniewtomanek/PycharmProjects/datawalk-entity-resolution`
   - Read `README.md` to confirm it's the right repo (should mention entity resolution, Vertica, Fellegi-Sunter)
   - This is reference-only -- episode content is pre-written in `resources/episodes.md`

4. **Verify remember tool**
   - Store a single test episode as a smoke test:
     ```
     remember(
       text="Plan 18.5 revalidation test marker -- ignore this episode",
       context="e2e_revalidation_smoketest",
       importance=0.1
     )
     ```
   - Confirm it returns an `episode_id`
   - This episode has low importance and won't interfere with recall measurements

---

## Verification

- [ ] `discover_graphs` returns successfully
- [ ] Baseline graph state recorded (node/edge/episode counts, or "empty")
- [ ] Source repo at `/Users/zbigniewtomanek/PycharmProjects/datawalk-entity-resolution` is accessible
- [ ] Smoke test `remember` call returns an `episode_id`

---

## Outputs

Record in the index.md progress tracker notes:
- Baseline graph state (existing counts)
- Smoke test episode_id
- Any issues with MCP connectivity
