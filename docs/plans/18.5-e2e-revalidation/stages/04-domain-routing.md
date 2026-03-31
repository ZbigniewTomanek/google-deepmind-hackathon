# Stage 4: Domain Routing Validation

**Goal**: Measure domain routing success rate (M5) -- what fraction of the 28 episodes were classified to at least one semantic domain.
**Dependencies**: Stage 3 (Extraction Wait) must be DONE

---

## Steps

1. **Discover available domains**
   - Call `discover_domains` (if available) or `discover_graphs` to list all graphs
   - Look for shared domain graphs with names like:
     - `ncx_shared__technical_knowledge`
     - `ncx_shared__work_context`
     - `ncx_shared__domain_knowledge`
     - `ncx_shared__user_profile`
   - Record which shared graphs exist and their sizes (node/edge counts)

2. **Check for domain graph content**
   - For each shared domain graph that exists, call `discover_ontology(graph_name=...)`
   - If a shared graph has nodes, it means episodes were successfully routed to it
   - Record the node count per domain graph

3. **Estimate routing success rate**
   - The original E2E had 0/28 episodes classified (0% routing success)
   - Plan 18 Stage 4 fixed: empty-domains guard + keyword fallback + seed_defaults
   - Count how many shared domain graphs have content:
     - Technical keywords (python, database, api, architecture, code, framework, library) -> `technical_knowledge`
     - Work keywords (project, task, team, meeting, sprint, deadline, milestone) -> `work_context`
     - Domain keywords (concept, theory, fact, research) -> `domain_knowledge`
   - Most of our 28 episodes contain technical + work keywords, so routing should be high

4. **Measure M5**
   - **Ideal measurement**: Count episodes that were classified to >= 1 domain
   - **Practical measurement**: If per-episode routing data isn't directly visible via MCP tools, infer from:
     - Presence of shared domain graphs (did any get created?)
     - Node/edge counts in shared graphs (were episodes extracted into them?)
     - Compare to personal graph: if shared graphs have content = routing worked
   - Record the measurement:
     ```
     M5: Domain routing success rate
     Baseline: 0% (0/28)
     Target: >= 75% (21/28)
     Measured: [X]% ([N]/28)
     Verdict: PASS / FAIL
     ```

5. **Analyze routing distribution**
   - If routing succeeded, check distribution across domains:
     ```
     | Domain | Episodes Routed | Example Content |
     |--------|----------------|-----------------|
     | technical_knowledge | ... | ... |
     | work_context | ... | ... |
     | domain_knowledge | ... | ... |
     | user_profile | ... | ... |
     ```
   - Note: domain_knowledge is the fallback -- if keyword matching can't find a specific domain, episodes go here

---

## Important Notes

- Domain routing success is measured by whether episodes get classified at all, not whether they go to the "right" domain
- The keyword fallback (Plan 18 Stage 4) should catch most episodes even if the LLM classifier is conservative
- If no shared graphs exist at all, this indicates seed_defaults may not have run in the job context
- Check the personal graph too -- it should contain all episodes regardless of domain routing

---

## Verification

- [ ] Shared domain graphs inspected (existence + sizes)
- [ ] M5 measurement recorded with numeric value
- [ ] Routing distribution analyzed (if routing succeeded)
- [ ] Verdict (PASS/FAIL) determined against >= 75% target

---

## Outputs

Record in the index.md progress tracker notes:
- "M5: [X]% ([N]/28 episodes routed) -- PASS/FAIL"
- Which domain graphs have content
- Any routing anomalies
