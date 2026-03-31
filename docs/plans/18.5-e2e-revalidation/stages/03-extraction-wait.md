# Stage 3: Extraction Wait & Monitoring

**Goal**: Wait for the extraction pipeline to consolidate all 28 episodes into graph nodes and edges, monitoring progress.
**Dependencies**: Stage 2 (Episode Ingestion) must be DONE

---

## Steps

1. **Initial wait**
   - The extraction pipeline processes ~1.3 episodes/minute (3-agent LLM pipeline)
   - 28 episodes will take approximately **22 minutes** to fully process
   - Wait at least 5 minutes before the first progress check

2. **Monitor extraction progress**
   - Call `discover_graphs` periodically to check graph growth
   - Look at the personal graph's node count, edge count, and episode count
   - Compare to baseline from Stage 1

3. **Poll until stable**
   - Repeat `discover_graphs` every 3-5 minutes
   - Extraction is complete when node and edge counts stabilize (two consecutive checks show same counts)
   - Track progress:
     ```
     | Check # | Time | Nodes | Edges | Episodes | Delta |
     |---------|------|-------|-------|----------|-------|
     | 1 | +5min | ... | ... | ... | ... |
     | 2 | +10min | ... | ... | ... | ... |
     | ... | | | | | |
     ```

4. **Record final graph statistics**
   - Once stable, record:
     - Total nodes (minus baseline)
     - Total edges (minus baseline)
     - Total episodes (should be 28 + 1 smoke test = 29)
     - Consolidation rate: what fraction of episodes are consolidated?
   - Compare to original E2E: 121 nodes, 45 edges from 19/28 extracted episodes

5. **Assess extraction completeness**
   - If fewer than 20/28 episodes are consolidated after 30 minutes, note this but continue
   - The recall tests will still work on both consolidated nodes AND unconsolidated episodes
   - The unconsolidated episode boost (1.3x) should help fresh episodes surface

---

## Important Notes

- **Be patient** -- don't rush this stage. Premature recall testing will see mostly episodes (not nodes) and won't test the full scoring pipeline
- If extraction seems stalled (zero node growth for 10+ minutes), check:
  - Is the MCP server still running?
  - Call `discover_graphs` to verify connectivity
  - The extraction workers may have hit rate limits on the Gemini API
- Domain routing happens in parallel with extraction -- episodes are classified to domains during this stage

---

## Verification

- [ ] Graph node count is growing (extraction is running)
- [ ] Counts stabilized after sufficient wait (extraction complete)
- [ ] Final graph statistics recorded
- [ ] At least 15/28 episodes consolidated (>50%)

---

## Outputs

Record in the index.md progress tracker notes:
- Final counts: "N nodes, M edges, K/28 episodes consolidated"
- Total wait time
- Any extraction issues observed
