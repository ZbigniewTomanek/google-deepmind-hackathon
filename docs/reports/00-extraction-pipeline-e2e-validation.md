# Report 00 — Extraction Pipeline E2E Validation

> **Date:** 2026-03-27
> **Plan:** [07-extraction-pipeline-integration](../plans/07-extraction-pipeline-integration.md)
> **Status:** PASS
> **Commit:** `7a4e031` (fix: resolve race condition in type upsert, case-sensitive node match, and add safety guards)

## Objective

Validate the end-to-end knowledge extraction pipeline: ingest medical-domain text, run the 3-agent extraction pipeline (ontology, extractor, librarian), persist to PostgreSQL knowledge graph, and verify retrieval via recall with graph-traversal context.

## Environment

| Component | Version / Config |
|-----------|-----------------|
| Python | 3.13 |
| PostgreSQL | 16 (pgvector, Docker) |
| Extraction model | `gemini-2.5-flash` via `pydantic-ai` GoogleModel |
| Embedding model | `gemini-embedding-001` (768-dim) |
| Auth mode | `none` (agent_id = `anonymous`) |
| Schema | `ncx_anonymous__personal` |

## Test Corpus

10 medical-domain episodes ingested via `python -m neocortex.extraction.cli --ingest-corpus`:

| # | Title |
|---|-------|
| 1 | Serotonin and Mood Regulation |
| 2 | SSRIs: Mechanism and Clinical Use |
| 3 | SSRI-Induced Sexual Dysfunction |
| 4 | Dopamine Pathways and Reward |
| 5 | PDE5 Inhibitors in Erectile Dysfunction |
| 6 | Neuroanatomy of Sexual Response |
| 7 | Antiepileptic Drugs and Hormonal Effects |
| 8 | Multiple Sclerosis and Sexual Dysfunction |
| 9 | Bupropion: Atypical Antidepressant Profile |
| 10 | Neuroplasticity and Pharmacological Intervention |

## Results

### Job Queue

All 10 extraction jobs completed successfully. Each job took ~60-90 seconds (3 sequential Gemini API calls per job).

```
  status   | count
-----------+-------
 succeeded |    10
```

### Knowledge Graph

| Metric | Count |
|--------|------:|
| Nodes | 258 |
| Edges | 268 |
| Node types | 28 |
| Edge types | 45 |
| Episodes | 10 |

#### Top Node Types by Count

| Type | Count |
|------|------:|
| AnatomicalStructure | 39 |
| PhysiologicalFunction | 37 |
| Disease | 30 |
| PathologicalCondition | 23 |
| BiologicalProcess | 20 |
| Concept | 18 |
| Drug | 16 |
| Receptor | 12 |
| DrugClass | 11 |
| TherapeuticStrategy | 7 |

#### Top Edge Types by Count

| Type | Count |
|------|------:|
| ASSOCIATED_WITH | 40 |
| TREATS | 24 |
| BELONGS_TO | 22 |
| FOUND_IN | 17 |
| INHIBITS | 14 |
| REGULATES | 11 |
| AUGMENTS | 11 |
| HAS_ADVERSE_EFFECT | 10 |
| CONTROLS | 9 |
| ORIGINATES_IN | 9 |

### Recall Validation

Query: `"serotonin"`, limit: 10

**Episode results** (8 returned, ranked by hybrid score):

| Rank | Episode | Score | Source |
|------|---------|------:|--------|
| 1 | #1 Serotonin and Mood Regulation | 0.849 | ingestion_text |
| 2 | #2 SSRIs: Mechanism and Clinical Use | 0.782 | ingestion_text |
| 3 | #6 Neuroanatomy of Sexual Response | 0.761 | ingestion_text |
| 4 | #3 SSRI-Induced Sexual Dysfunction | 0.758 | ingestion_text |
| 5 | #4 Dopamine Pathways and Reward | 0.756 | ingestion_text |
| 6 | #10 Neuroplasticity and Pharmacological Intervention | 0.732 | ingestion_text |
| 7 | #9 Bupropion: Atypical Antidepressant Profile | 0.721 | ingestion_text |
| 8 | #7 Antiepileptic Drugs and Hormonal Effects | 0.699 | ingestion_text |

**Node results with graph context** (2 returned, depth=2):

| Node | Type | Neighbors | Edges |
|------|------|----------:|------:|
| Serotonin Transporter | NeuralCircuit | 44 | 44 |
| Synaptic Cleft | Concept | 26 | 26 |

Graph context for "Serotonin Transporter" includes neighbor nodes: Serotonin (ChemicalClass), SSRIs, Raphe Nuclei, Dopamine, Major Depressive Disorder, 5-HT2A, Tryptophan, and edge types: IMPLICATED_IN, TREATS, USES, IMPAIRS, ACTIVATES, HAS_ADVERSE_EFFECT, COORDINATES, INDUCES.

### Discover Validation

| Field | Value |
|-------|-------|
| `stats.total_nodes` | 258 |
| `stats.total_edges` | 268 |
| `stats.total_episodes` | 10 |
| Node types returned | 28 |
| Edge types returned | 45 |
| Graphs accessible | `ncx_anonymous__personal`, `ncx_shared__knowledge` |

Medical domain types present: AnatomicalStructure, BiologicalProcess, Disease, Drug, DrugClass, Enzyme, Neurotransmitter, Receptor, ReceptorFamily, TherapeuticStrategy, Transporter.

### Structured Logging

Log files created and populated:

| File | Content |
|------|---------|
| `log/mcp.log` | Service log with PostgreSQL connect, embedding init, request handling |
| `log/ingestion.log` | Ingestion API service log |
| `log/agent_actions.log` | JSON audit trail, filtered by `action_log=True` |

Sample audit entry from `agent_actions.log`:

```json
{
  "text": "recall_with_graph_traversal",
  "record": {
    "extra": {
      "action_log": true,
      "agent_id": "anonymous",
      "query": "dopamine",
      "total_results": 8,
      "node_results_with_context": 5
    },
    "level": { "name": "INFO" },
    "name": "neocortex.tools.recall",
    "function": "recall",
    "line": 111
  }
}
```

### Pipeline Traces

Server logs show correct extraction lifecycle per job:

```
extract_episode_started
  Using GoogleModel model_name=gemini-2.5-flash  (x3 — one per agent)
  extraction_start
  extraction_complete
extract_episode_completed
```

## Bugs Fixed During Validation

These were resolved before this validation run. See [handover.md](../../handover.md) for details.

| # | Issue | File(s) |
|---|-------|---------|
| 1 | `PostgresConfig` rejects extra env vars | `config.py` |
| 2 | Procrastinate schema apply not idempotent | `services.py` |
| 3 | `defer_async` writes to InMemoryConnector | `episode_processor.py`, `remember.py`, `jobs/__init__.py` |
| 4 | Jobs enqueued to wrong queue (`default`) | `jobs/__init__.py` |
| 5 | Missing UNIQUE constraint on edge table | `graph_schema.sql` |
| 6 | Test mocks outdated for new defer pattern | `test_remember_extraction.py` |

## Reproduction

See [E2E Reproduction Guide](../e2e-reproduction.md) for step-by-step instructions.

## Conclusion

The extraction pipeline is fully functional end-to-end. All 10 episodes were ingested, extracted by the 3-agent pipeline, and persisted as a knowledge graph with 258 nodes and 268 edges across 28 node types and 45 edge types. Recall returns episodes ranked by hybrid score with graph-traversal context. Discover returns the full ontology with counts. Structured logging captures audit entries for all MCP tool invocations.
