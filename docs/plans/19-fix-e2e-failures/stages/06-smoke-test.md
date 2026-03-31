# Stage 6: Integration Smoke Test

**Goal**: Verify all 3 fixes work end-to-end by storing targeted episodes via MCP tools and checking graph state.
**Dependencies**: Stages 1-5 must be DONE. MCP server must be running with real DB.

---

## Background

This stage is executed by Claude with MCP access, similar to Plan 18.5. It stores 3 specific episodes and validates that:
1. Domain routing populates shared graphs (M5 fix)
2. Correction episodes create SUPERSEDES/CORRECTS edges (M4 fix)
3. No corrupted type names appear (M6 fix)

---

## Steps

### Pre-flight

1. Start the MCP server and ingestion service:
   ```bash
   ./scripts/launch.sh
   ```

2. Verify MCP tools are functional:
   - Call `discover_graphs` -- should list personal and shared graphs
   - Call `discover_domains` -- should list 4 seed domains

### Episode 1: Technical knowledge (domain routing test)

3. Store via `remember`:
   ```
   text: "The DataWalk entity resolution system uses a dual-projection Vertica architecture
   with blocking-based candidate generation. The system implements Fellegi-Sunter probabilistic
   matching with information content weighting. Key components: BlockingService (Python),
   MatchingEngine (SQL/Vertica), and a React dashboard for review workflows."
   importance: 0.7
   ```

4. Wait for extraction (2-3 minutes), then verify:
   - `discover_graphs` -- shared graphs should have non-zero node counts
   - Check `ncx_shared__technical_knowledge` specifically via `discover_ontology`
   - **Pass criteria**: At least 1 shared graph has nodes from this episode

### Episode 2: Correction (temporal edge test)

5. Store a base fact via `remember`:
   ```
   text: "The Metaphone3 phonetic encoding uses a 4-character code length for all languages.
   This was decided in sprint 12 based on benchmark results showing 87% accuracy on the
   English test corpus."
   importance: 0.6
   ```

6. Wait for extraction (2-3 minutes).

7. Store a correction via `remember`:
   ```
   text: "CORRECTION: The Metaphone3 strategy has been updated. Instead of using 4-char
   codes for all languages, the team switched to a hybrid approach: 8-character codes
   for Latin-script languages and 4-character codes for non-Latin scripts. This replaced
   the previous uniform 4-char strategy after discovering precision issues with longer names."
   importance: 0.8
   ```

8. Wait for extraction (2-3 minutes), then verify:
   - `discover_ontology` -- check for SUPERSEDES or CORRECTS edge types with instances
   - `inspect_node` on "Metaphone3" or similar -- check for temporal edges in neighborhood
   - **Pass criteria**: At least 1 SUPERSEDES or CORRECTS edge exists connecting the correction to the original

### Episode 3: Clean type names (type corruption test)

9. Store via `remember`:
   ```
   text: "The normalization pipeline preprocesses input records through multiple stages:
   phone number parsing (ParsePhoneNumber UDX), human name parsing (ParseHumanName UDX),
   address standardization, and Unicode normalization. Each stage produces a normalized
   field that feeds into the composite fingerprint computation."
   importance: 0.5
   ```

10. Wait for extraction (2-3 minutes), then verify:
    - `discover_ontology` -- scan ALL node type names
    - Check every type against: starts with uppercase, <= 60 chars, no embedded IDs
    - **Pass criteria**: Zero corrupted type names

### Cleanup

11. Record all results in this stage file.
12. Stop services: `./scripts/launch.sh --stop`

---

## Verification

| Check | Pass Criteria |
|-------|--------------|
| Domain routing | >= 1 shared graph has nodes after Episode 1 |
| Temporal edges | >= 1 SUPERSEDES or CORRECTS edge after Episode 3 (correction) |
| Type names | 0 corrupted types across all extractions |
| Server stability | No crashes, no unhandled exceptions in logs |

---

## Commit

```
docs(plan-19): record integration smoke test results

Stage 6: MCP-driven smoke test verified domain routing, temporal
correction edges, and type name integrity end-to-end.
```
