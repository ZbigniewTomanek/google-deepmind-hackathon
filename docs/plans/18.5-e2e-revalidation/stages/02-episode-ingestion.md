# Stage 2: Episode Ingestion

**Goal**: Store all 28 episodes from `resources/episodes.md` via the `remember` MCP tool, recording each episode ID.
**Dependencies**: Stage 1 (Setup & Baseline) must be DONE

---

## Steps

1. **Read episode data**
   - Read `resources/episodes.md` for the full text, importance, and context of all 28 episodes

2. **Store Phase 1 episodes (1--8)**
   - For each episode in Phase 1 (Onboarding), call:
     ```
     remember(
       text=<episode text from resources/episodes.md>,
       context=<context value>,
       importance=<importance value>
     )
     ```
   - Record the returned `episode_id` for each
   - Episodes 1-8 simulate January 2026 onboarding

3. **Store Phase 2 episodes (9--17)**
   - Same process for Phase 2 (Active Development)
   - Episodes 9-17 simulate February 2026 active work
   - Pay special attention to episodes that will be recall targets:
     - Episode 10 (SQL injection) -- importance 0.7
     - Episode 15 (birthday paradox fingerprint fix) -- importance 0.6
     - Episode 16 (Korean character crash) -- importance 0.6

4. **Store Phase 3 episodes (18--25)**
   - Same process for Phase 3 (Scaling & Optimization)
   - Key episodes for temporal chain:
     - Episode 18 (Metaphone3 4-char concerns) -- importance 0.7
     - Episode 20 (switch to 8-char) -- importance 0.7
   - Key episode for gravity well test:
     - Episode 24 (Fellegi-Sunter gap analysis) -- importance 0.8

5. **Store Phase 4 episodes (26--28)**
   - Same process for Phase 4 (Evolution & Corrections)
   - Critical episodes:
     - Episode 26 (CORRECTION: Metaphone3 hybrid) -- importance 0.8, text contains "CORRECTION"
     - Episode 27 (team change: Jonas to security) -- importance 0.6
     - Episode 28 (duplicate prevalence discovery) -- importance 0.7

6. **Record episode ID mapping**
   - Create a table mapping episode number -> episode_id for reference:
     ```
     | Episode # | episode_id | Phase | Topic |
     |-----------|-----------|-------|-------|
     | 1 | ... | 1 | Project Overview |
     | 2 | ... | 1 | Team Composition |
     | ... | ... | ... | ... |
     | 28 | ... | 4 | Duplicate Prevalence |
     ```

---

## Important Notes

- Use the **exact text** from `resources/episodes.md` -- do not paraphrase or shorten
- Set the **exact importance** value specified for each episode
- Set the **exact context** string specified for each episode
- Do NOT set `target_graph` -- let the system route automatically (personal + domain routing)
- Episodes can be stored sequentially; no need for parallelism
- After all 28 are stored, the extraction pipeline will begin processing asynchronously

---

## Verification

- [ ] All 28 episodes stored successfully (each returned an episode_id)
- [ ] Episode ID mapping table recorded with all 28 entries
- [ ] No errors during storage

---

## Outputs

Record in the index.md progress tracker notes:
- "28 episodes stored, IDs: [first]--[last]"
- Any storage failures or errors
