# Plan: Pydantic AI BMW Ontology Demo

## Overview
Build a small teaching-quality demo under `src/pydantic_agents_playground` that shows how to use Pydantic AI with Google Gemini to process a stream of BMW 3 Series messages. The demo will use a moderately detailed ontology, preserve accepted ontology-change history in SQLite, and deduplicate repeated facts globally while keeping per-message provenance. It will read 10 predefined messages one by one. For each message it will:

1. load the current ontology and already-known facts from SQLite
2. ask an ontology agent to propose a conservative OWL-like ontology extension
3. ask an extractor agent to extract facts that fit the updated ontology
4. ask a librarian agent to normalize the extracted output into a persistence payload
5. write the accepted ontology and facts into SQLite

The demo is intentionally narrow. It is not a full ontology engine, not a general knowledge graph platform, and not a production ingestion pipeline. The goal is to make the Pydantic AI agent flow easy to understand, run, and inspect.

## Why This Plan Is Detailed
This document is written so a person with no prior Pydantic AI knowledge can implement it by following the steps exactly. It names the expected files, classes, functions, tables, prompts, verification commands, and the data shape passed between agents.

## Pydantic AI Primer

### Core concepts this demo will use
- `Agent`: the main Pydantic AI object. It wraps a model, instructions, and an output schema.
- `output_type`: a Pydantic model that defines the structured result the model must return.
- `deps_type`: a Python type describing runtime dependencies passed into an agent at call time.
- `RunContext`: the object used inside dynamic instructions or tools to read `deps`.
- `run_sync(...)`: the simplest way to execute an agent in a CLI demo.
- `result.output`: the parsed structured output returned by the agent.

### The exact pattern to follow
Use this shape for each agent:

```python
from pydantic_ai import Agent
from pydantic_ai.models.google import GoogleModel

model = GoogleModel("gemini-3-flash-preview", provider="google-gla")

agent = Agent(
    model=model,
    output_type=SomePydanticModel,
    deps_type=SomeDepsDataclass,
    system_prompt="Static role instructions here",
)

result = agent.run_sync("Task-specific user prompt here", deps=deps)
parsed_output = result.output
```

### Offline verification mode
For a local smoke test without API credentials, the implementation should support using `pydantic_ai.models.test.TestModel` instead of Gemini. This mode is only for wiring verification. The real demo target remains `google-gla:gemini-3-flash-preview`.

## Scope

### In scope
- a fixed corpus of 10 BMW 3 Series messages written from general model knowledge
- three distinct Pydantic AI agents
- structured outputs validated with Pydantic models
- SQLite persistence for ontology snapshot tables, ontology history tables, canonical facts, fact provenance, and processing runs
- a CLI that can run the full pipeline from scratch
- documentation showing how to run with Gemini and how to inspect the database

### Out of scope
- OWL serialization to RDF/XML or Turtle
- advanced ontology reasoning
- embeddings, retrieval, or vector search
- concurrent processing
- a web UI
- production-grade migration tooling

## Architecture Decision

### Chosen orchestration style
Use programmatic hand-off in Python rather than one supervising agent with tool calls.

### Why
- the sequence is fixed
- SQLite writes should stay deterministic
- a novice can debug ordinary Python code more easily than nested agent tool chains
- this still qualifies as an agentic system because each stage is its own Pydantic AI agent with its own role and structured output

## Runtime Behavior

### Inputs
- 10 hard-coded BMW 3 Series messages in Python
- each message has:
  - `message_id`
  - `title`
  - `topic`
  - `content`

### Per-message flow
For each message in ascending order:

1. read the current ontology snapshot from SQLite
2. create `OntologyAgentDeps` with:
   - current classes
   - current properties
   - current message
3. call the ontology agent
4. merge the ontology proposal into an in-memory candidate ontology
5. create `ExtractorAgentDeps` with:
   - current message
   - candidate ontology
6. call the extractor agent
7. create `LibrarianAgentDeps` with:
   - current message
   - candidate ontology
   - extracted entities
   - extracted facts
   - known entity IDs
8. call the librarian agent
9. persist the librarian output into SQLite inside one transaction
10. record a processing-run row summarizing what changed

### Output
After all 10 messages are processed, the database should contain:
- the source messages
- the current ontology classes
- the current ontology properties
- entities extracted from messages
- canonical fact assertions deduplicated globally
- fact provenance mentions linked to source messages
- one processing run row per message

## File Layout
Create the following files under `src/pydantic_agents_playground/`:

- `__init__.py`
  - package marker
- `__main__.py`
  - allows `python -m pydantic_agents_playground`
- `messages.py`
  - the fixed list of 10 BMW messages
- `schemas.py`
  - all Pydantic models and dependency dataclasses
- `database.py`
  - SQLite schema creation and repository methods
- `agents.py`
  - the three Pydantic AI agent definitions
- `pipeline.py`
  - orchestration loop for processing all messages
- `cli.py`
  - argument parsing and top-level `main()`

Do not split further unless the code becomes too large. This package should stay small.

## Concrete Data Contracts

### Shared message model
Define this in `schemas.py`:

```python
class SeedMessage(BaseModel):
    message_id: str
    title: str
    topic: str
    content: str
```

### Ontology structures
Use a lightweight OWL-like structure. Keep it generic first, but allow moderately detailed BMW-specific concepts when they materially help explain the 10-message corpus.

```python
class OntologyClass(BaseModel):
    class_id: str
    label: str
    description: str
    parent_class_id: str | None = None


class OntologyProperty(BaseModel):
    property_id: str
    label: str
    description: str
    domain_class_id: str
    value_type: Literal["string", "number", "boolean", "date", "entity"]
    range_class_id: str | None = None
    multi_valued: bool = False
```

### Ontology agent output
The ontology agent should only propose additions or clarifications. It should not rewrite the whole ontology.

```python
class OntologyProposal(BaseModel):
    new_classes: list[OntologyClass] = Field(default_factory=list)
    new_properties: list[OntologyProperty] = Field(default_factory=list)
    rationale: str
```

Rules for the prompt:
- prefer generic classes like `CarModel`, `Engine`, `RacingSeries`, `Generation`, `BodyStyle`
- allow BMW-specific classes or properties when they help explain the corpus and are likely to recur
- avoid creating a new class for every single trim, engine code, or marketing label unless truly needed
- prefer extending with properties before creating new classes
- do not delete or rename existing ontology items

### Extractor agent output
The extractor agent should emit ontology-aligned data only.

```python
class ExtractedEntity(BaseModel):
    entity_id: str
    label: str
    class_id: str
    canonical_name: str


class ExtractedFact(BaseModel):
    subject_entity_id: str
    property_id: str
    value_type: Literal["string", "number", "boolean", "date", "entity"]
    string_value: str | None = None
    number_value: float | None = None
    boolean_value: bool | None = None
    date_value: str | None = None
    target_entity_id: str | None = None
    evidence_text: str
    confidence: float


class ExtractionResult(BaseModel):
    entities: list[ExtractedEntity] = Field(default_factory=list)
    facts: list[ExtractedFact] = Field(default_factory=list)
    rationale: str
```

Rules for the prompt:
- only use `property_id` values present in the candidate ontology
- create entities only when the message clearly refers to a concrete object
- include a short evidence snippet for every fact
- if a fact cannot fit the ontology, omit it instead of inventing a property

### Librarian agent output
The librarian is the last decision point before persistence. It should normalize IDs, reject malformed data, and emit the final payload that application code writes to SQLite.

```python
class PersistedEntity(BaseModel):
    entity_id: str
    label: str
    class_id: str
    canonical_name: str


class PersistedFact(BaseModel):
    subject_entity_id: str
    property_id: str
    value_type: Literal["string", "number", "boolean", "date", "entity"]
    string_value: str | None = None
    number_value: float | None = None
    boolean_value: bool | None = None
    date_value: str | None = None
    target_entity_id: str | None = None


class PersistedFactMention(BaseModel):
    subject_entity_id: str
    property_id: str
    value_type: Literal["string", "number", "boolean", "date", "entity"]
    string_value: str | None = None
    number_value: float | None = None
    boolean_value: bool | None = None
    date_value: str | None = None
    target_entity_id: str | None = None
    source_message_id: str
    evidence_text: str
    confidence: float


class LibrarianPayload(BaseModel):
    accepted_classes: list[OntologyClass] = Field(default_factory=list)
    accepted_properties: list[OntologyProperty] = Field(default_factory=list)
    entities_to_upsert: list[PersistedEntity] = Field(default_factory=list)
    canonical_facts_to_upsert: list[PersistedFact] = Field(default_factory=list)
    fact_mentions_to_insert: list[PersistedFactMention] = Field(default_factory=list)
    summary: str
```

Rules for the prompt:
- keep ontology additions moderately detailed but reusable
- reject duplicate ontology additions
- reject facts that reference missing entities or missing properties
- preserve provenance by always filling `source_message_id` on fact mentions
- do not invent values not present in the current message or ontology proposal
- if a fact already exists globally, keep the canonical fact once and add a new provenance mention for the current message

## Dependency Dataclasses
Define these in `schemas.py` with `@dataclass`.

```python
@dataclass
class OntologyAgentDeps:
    message: SeedMessage
    existing_classes: list[OntologyClass]
    existing_properties: list[OntologyProperty]


@dataclass
class ExtractorAgentDeps:
    message: SeedMessage
    classes: list[OntologyClass]
    properties: list[OntologyProperty]


@dataclass
class LibrarianAgentDeps:
    message: SeedMessage
    classes: list[OntologyClass]
    properties: list[OntologyProperty]
    extracted_entities: list[ExtractedEntity]
    extracted_facts: list[ExtractedFact]
    known_entity_ids: list[str]
    known_fact_signatures: list[str]
```

## SQLite Schema
Implement schema creation in `database.py` using `sqlite3`.

### Table: `messages`
- `message_id TEXT PRIMARY KEY`
- `title TEXT NOT NULL`
- `topic TEXT NOT NULL`
- `content TEXT NOT NULL`

### Table: `ontology_classes`
- `class_id TEXT PRIMARY KEY`
- `label TEXT NOT NULL`
- `description TEXT NOT NULL`
- `parent_class_id TEXT NULL`

### Table: `ontology_class_history`
- `history_id INTEGER PRIMARY KEY AUTOINCREMENT`
- `message_id TEXT NOT NULL`
- `class_id TEXT NOT NULL`
- `label TEXT NOT NULL`
- `description TEXT NOT NULL`
- `parent_class_id TEXT NULL`
- `change_type TEXT NOT NULL`
- `created_at TEXT NOT NULL`

### Table: `ontology_properties`
- `property_id TEXT PRIMARY KEY`
- `label TEXT NOT NULL`
- `description TEXT NOT NULL`
- `domain_class_id TEXT NOT NULL`
- `value_type TEXT NOT NULL`
- `range_class_id TEXT NULL`
- `multi_valued INTEGER NOT NULL`

### Table: `ontology_property_history`
- `history_id INTEGER PRIMARY KEY AUTOINCREMENT`
- `message_id TEXT NOT NULL`
- `property_id TEXT NOT NULL`
- `label TEXT NOT NULL`
- `description TEXT NOT NULL`
- `domain_class_id TEXT NOT NULL`
- `value_type TEXT NOT NULL`
- `range_class_id TEXT NULL`
- `multi_valued INTEGER NOT NULL`
- `change_type TEXT NOT NULL`
- `created_at TEXT NOT NULL`

### Table: `entities`
- `entity_id TEXT PRIMARY KEY`
- `label TEXT NOT NULL`
- `class_id TEXT NOT NULL`
- `canonical_name TEXT NOT NULL`

### Table: `facts`
- `fact_id TEXT PRIMARY KEY`
- `subject_entity_id TEXT NOT NULL`
- `property_id TEXT NOT NULL`
- `value_type TEXT NOT NULL`
- `string_value TEXT NULL`
- `number_value REAL NULL`
- `boolean_value INTEGER NULL`
- `date_value TEXT NULL`
- `target_entity_id TEXT NULL`
- `fact_signature TEXT NOT NULL UNIQUE`

### Table: `fact_mentions`
- `mention_id TEXT PRIMARY KEY`
- `fact_id TEXT NOT NULL`
- `source_message_id TEXT NOT NULL`
- `evidence_text TEXT NOT NULL`
- `confidence REAL NOT NULL`
- unique key recommendation: `(fact_id, source_message_id, evidence_text)`

### Table: `processing_runs`
- `run_id INTEGER PRIMARY KEY AUTOINCREMENT`
- `message_id TEXT NOT NULL`
- `new_class_count INTEGER NOT NULL`
- `new_property_count INTEGER NOT NULL`
- `entity_count INTEGER NOT NULL`
- `canonical_fact_count INTEGER NOT NULL`
- `fact_mention_count INTEGER NOT NULL`
- `summary TEXT NOT NULL`
- `created_at TEXT NOT NULL`

### Required repository methods
Implement these functions or similarly named methods:
- `create_schema()`
- `reset_database()`
- `upsert_message(message: SeedMessage)`
- `load_ontology() -> tuple[list[OntologyClass], list[OntologyProperty]]`
- `load_known_entity_ids() -> list[str]`
- `load_known_fact_signatures() -> list[str]`
- `apply_librarian_payload(payload: LibrarianPayload) -> None`
- `record_processing_run(...)`
- `build_fact_signature(fact: PersistedFact | PersistedFactMention) -> str`
- `count_rows(table_name: str) -> int`

All writes for one message should happen in one transaction.

### Global fact deduplication rule
Canonical facts are deduplicated across all messages using a deterministic `fact_signature` built from:
- `subject_entity_id`
- `property_id`
- `value_type`
- the normalized literal value or `target_entity_id`

The repository, not the model, is responsible for building `fact_signature`, `fact_id`, and `mention_id`. This avoids relying on the LLM to generate stable identifiers.

## Agent Definitions
Implement these in `agents.py`.

### Shared model factory
Create one helper:

```python
def build_model(use_test_model: bool):
    if use_test_model:
        return TestModel()
    return GoogleModel("gemini-3-flash-preview", provider="google-gla")
```

### Ontology agent
Name: `build_ontology_agent(...)`

Configuration:
- `output_type=OntologyProposal`
- `deps_type=OntologyAgentDeps`
- static system prompt explains the ontology role
- dynamic instructions should summarize:
  - current message
  - current ontology classes
  - current ontology properties
  - ontology extension rules

The user prompt can stay simple, for example:
- `"Propose ontology additions needed for this message."`

### Extractor agent
Name: `build_extractor_agent(...)`

Configuration:
- `output_type=ExtractionResult`
- `deps_type=ExtractorAgentDeps`
- dynamic instructions should summarize:
  - current message
  - the ontology the extractor must obey
  - the rule that only ontology-aligned facts are allowed

The user prompt can stay simple:
- `"Extract entities and facts for this message using only the provided ontology."`

### Librarian agent
Name: `build_librarian_agent(...)`

Configuration:
- `output_type=LibrarianPayload`
- `deps_type=LibrarianAgentDeps`
- dynamic instructions should summarize:
  - current message
  - candidate ontology
  - extractor results
  - known entity IDs
  - known fact signatures
  - normalization rules

The user prompt can stay simple:
- `"Prepare the final ontology and fact payload for persistence."`

## Prompting Rules
Write the system prompts as short operational rules, not essays.

### Ontology prompt must say
- propose only reusable concepts
- extend conservatively
- do not remove existing items
- prefer generic automotive concepts first
- BMW-specific concepts are allowed when they are useful across multiple messages in this corpus

### Extractor prompt must say
- every fact must reference a valid `property_id`
- use `target_entity_id` only when `value_type="entity"`
- use the message text as the only evidence source
- do not guess missing numeric values
- prefer moderately detailed entities and facts when supported by the text

### Librarian prompt must say
- reject malformed records
- deduplicate ontology additions
- deduplicate facts globally using stable fact signatures
- preserve one provenance row per source message mention
- keep identifiers stable and machine-friendly

## Message Corpus
Create exactly 10 messages in `messages.py`. Each message should focus on one theme so ontology growth is easy to inspect. Write them from general assistant knowledge rather than copying a source. They should be plausible, concise, and lightly factual, but they do not need citation-grade precision.

Recommended themes:
1. E21 launch and compact executive positioning
2. E30 M3 homologation and touring car racing success
3. inline-six engines in the E36 and E46 era
4. E46 M3 CSL as a famous enthusiast model
5. diesel popularity of the 320d in Europe
6. turbocharged 335i and the N54 tuning reputation
7. wagon or Touring body style
8. xDrive all-wheel drive in later generations
9. plug-in hybrid 330e
10. G20 generation and M340i performance positioning

Aim for a moderately detailed corpus. It should naturally justify concepts like generations, motorsport homologation, engine families, drivetrains, body styles, and hybrid powertrains.

## Orchestration Logic
Implement this in `pipeline.py`.

### Required public API
```python
def run_demo(
    db_path: str,
    use_test_model: bool = False,
    reset_db: bool = False,
) -> DemoRunSummary:
    ...
```

### Execution steps inside `run_demo`
1. open `SQLiteRepository`
2. create schema if needed
3. optionally reset tables if `reset_db=True`
4. build the three agents once
5. loop over the 10 seed messages
6. insert the source message
7. load current ontology
8. run ontology agent
9. merge proposed classes and properties with current ontology in memory
10. run extractor agent against the merged ontology
11. load known entity IDs
12. load known fact signatures
13. run librarian agent
14. apply librarian payload
15. record processing run
16. build a human-readable summary object

### Ontology merge rule
Use simple ID-based deduplication:
- if a proposed `class_id` already exists, ignore the duplicate
- if a proposed `property_id` already exists, ignore the duplicate

Do not attempt fuzzy merging in version 1.

### Ontology history rule
Whenever a new class or property is accepted and inserted into the current snapshot table, also insert one immutable row into the matching history table with the current `message_id` and `change_type="accepted_addition"`.

The implementation does not need to store rejected ontology proposals in version 1.

## CLI
Implement this in `cli.py` and expose through `__main__.py`.

### Required CLI flags
- `--db-path`
  - default: `data/pydantic_agents_playground.sqlite`
- `--reset-db`
  - clears existing tables before processing
- `--use-test-model`
  - runs with `TestModel` instead of Gemini

### Required behavior
- create the parent directory for the SQLite file if missing
- print one short line per processed message showing:
  - message id
  - number of accepted ontology classes
  - number of accepted ontology properties
  - number of canonical facts upserted
  - number of fact mentions inserted
- print a final summary with total row counts

## Verification Strategy

### Mandatory local verification
Run these after implementation:

1. `uv run python -m pydantic_agents_playground --use-test-model --reset-db`
2. `uv run python -c "import sqlite3; conn = sqlite3.connect('data/pydantic_agents_playground.sqlite'); print(conn.execute('select count(*) from processing_runs').fetchone()[0])"`
3. `uv run ruff check src`
4. `uv run black --check src`

### Optional live verification
Only if `GOOGLE_API_KEY` is set:

1. `uv run python -m pydantic_agents_playground --reset-db`
2. inspect the resulting SQLite database
3. confirm the pipeline finishes all 10 messages without validation failures

## Failure Handling
- if an agent output fails validation, stop the run and print which agent failed
- if SQLite write fails, roll back the transaction for that message
- do not silently continue after schema or validation errors
- do not catch and ignore `pydantic.ValidationError`
- if a canonical fact already exists, insert only the new fact mention and skip creating a duplicate `facts` row

## Stage Plan

## Execution Protocol

To execute this plan, follow this loop for each stage:

1. read the progress tracker and find the first stage not marked `DONE`
2. read that stage completely before editing files
3. implement only that stage
4. run the listed verification steps
5. update the progress tracker
6. commit if commits are requested

If a stage becomes blocked, mark it `BLOCKED`, write the reason in `Issues`, and stop.

## Progress Tracker

| # | Stage | Status | Notes | Commit |
|---|-------|--------|-------|--------|
| 1 | Create package skeleton and shared schemas | DONE | Added package skeleton, shared Pydantic schemas, packaging metadata, and a schema smoke test. | `feat(pydantic-playground): add package skeleton and shared models` |
| 2 | Add seed messages and SQLite repository | DONE | Added the 10-message BMW corpus, SQLite repository schema/write helpers, transaction support, and persistence tests. | `feat(pydantic-playground): add corpus and sqlite persistence` |
| 3 | Implement ontology, extractor, and librarian agents | DONE | Added the shared model factory, three Pydantic AI agent builders with dynamic instructions, and agent builder tests. | `feat(pydantic-playground): add pydantic ai agents` |
| 4 | Implement orchestration pipeline and CLI | DONE | Added sequential runner, CLI parsing, per-message progress output, and offline pipeline tests. | `feat(pydantic-playground): add sequential demo runner` |
| 5 | Document and verify the demo | DONE | Added README runbook for offline and Gemini modes; verified `ruff`, `black`, offline CLI run, and `poetry run pytest`; offline `TestModel` path leaves ontology and fact tables empty. | `docs(pydantic-playground): document demo workflow` |

Statuses: `PENDING` -> `IN_PROGRESS` -> `DONE` | `BLOCKED`

Last stage completed: Document and verify the demo
Last updated by: plan-runner-agent

---

## Stage 1: Create package skeleton and shared schemas
**Goal**: Create the package and define all Pydantic models and dependency dataclasses before any agent or database code exists.
**Dependencies**: None

**Files**:
- `src/pydantic_agents_playground/__init__.py`
- `src/pydantic_agents_playground/__main__.py`
- `src/pydantic_agents_playground/schemas.py`

**Atomic steps**:
1. Create the package directory and empty `__init__.py`.
2. Add `__main__.py` that imports and calls `main` from `cli.py`.
3. In `schemas.py`, define all Pydantic models listed in this plan.
4. In `schemas.py`, define the three dependency dataclasses.
5. Add a small `DemoRunSummary` model for final CLI reporting.

**Verification**:
- [ ] `uv run python -c "from pydantic_agents_playground.schemas import SeedMessage, OntologyProposal"`
- [ ] imports succeed without touching the network

**Commit**: `feat(pydantic-playground): add package skeleton and shared models`

---

## Stage 2: Add seed messages and SQLite repository
**Goal**: Add the fixed corpus and the full SQLite persistence layer.
**Dependencies**: Stage 1

**Files**:
- `src/pydantic_agents_playground/messages.py`
- `src/pydantic_agents_playground/database.py`

**Atomic steps**:
1. Add the 10 BMW messages in `messages.py` as a constant list of `SeedMessage`.
2. Implement repository initialization and schema creation in `database.py`.
3. Add load methods for ontology and known entity IDs.
4. Add load method for known fact signatures.
5. Add write methods for messages, ontology snapshot rows, ontology history rows, entities, canonical facts, fact mentions, and processing runs.
6. Ensure one-message persistence happens inside one transaction.

**Verification**:
- [ ] `uv run python -c "from pydantic_agents_playground.messages import SEED_MESSAGES; print(len(SEED_MESSAGES))"`
- [ ] `uv run python -c "from pydantic_agents_playground.database import SQLiteRepository; repo = SQLiteRepository(':memory:'); repo.create_schema(); print('ok')"`

**Commit**: `feat(pydantic-playground): add corpus and sqlite persistence`

---

## Stage 3: Implement ontology, extractor, and librarian agents
**Goal**: Define the three Pydantic AI agents with structured outputs and dynamic instructions.
**Dependencies**: Stage 2

**Files**:
- `src/pydantic_agents_playground/agents.py`

**Atomic steps**:
1. Implement `build_model(use_test_model: bool)`.
2. Implement `build_ontology_agent(...)`.
3. Implement `build_extractor_agent(...)`.
4. Implement `build_librarian_agent(...)`.
5. Keep all prompts short and rule-based.
6. Use `deps_type` and dynamic instructions rather than building giant user prompts manually.

**Verification**:
- [ ] `uv run python -c "from pydantic_agents_playground.agents import build_model; print(build_model(True).__class__.__name__)"`
- [ ] module imports without calling the live API

**Commit**: `feat(pydantic-playground): add pydantic ai agents`

---

## Stage 4: Implement orchestration pipeline and CLI
**Goal**: Wire the agents and repository into one sequential demo runner with a usable CLI.
**Dependencies**: Stage 3

**Files**:
- `src/pydantic_agents_playground/pipeline.py`
- `src/pydantic_agents_playground/cli.py`

**Atomic steps**:
1. Implement `run_demo(...)` exactly as described in the orchestration section.
2. Build the three agents once at the start of the run.
3. Print concise progress lines for each message.
4. Return a final summary object for CLI use.
5. Add CLI argument parsing and default paths.

**Verification**:
- [ ] `uv run python -m pydantic_agents_playground --use-test-model --reset-db`
- [ ] the command creates the SQLite file and 10 `processing_runs` rows

**Commit**: `feat(pydantic-playground): add sequential demo runner`

---

## Stage 5: Document and verify the demo
**Goal**: Explain how to run the demo and confirm the offline path works.
**Dependencies**: Stage 4

**Files**:
- `README.md`

**Atomic steps**:
1. Add a short section describing the package purpose.
2. Add commands for offline test-model mode.
3. Add commands for live Gemini mode with `GOOGLE_API_KEY`.
4. Add a short note describing where the SQLite database is written and which tables to inspect.
5. Run the mandatory local verification commands and record any caveats.

**Verification**:
- [ ] `uv run ruff check src`
- [ ] `uv run black --check src`
- [ ] `uv run python -m pydantic_agents_playground --use-test-model --reset-db`

**Commit**: `docs(pydantic-playground): document demo workflow`

## Overall Verification
- run the offline path from a clean database and confirm 10 messages are processed
- inspect SQLite and confirm non-zero row counts in `ontology_classes`, `ontology_class_history`, `ontology_properties`, `ontology_property_history`, `entities`, `facts`, `fact_mentions`, and `processing_runs`
- if credentials are available, run the live Gemini path and confirm the model name used is `gemini-3-flash-preview` via the Google GLA provider

## Resolved Decisions

### Decision: Ontology detail level
- Chosen: moderately detailed
- Effect on implementation: allow BMW-specific concepts when they meaningfully explain the corpus, but still prefer generic automotive classes and properties where possible

### Decision: Ontology history retention
- Chosen: full history of accepted ontology changes only
- Effect on implementation: keep current snapshot tables for easy loading and separate immutable history tables for accepted additions per message; rejected proposals are not stored

### Decision: Fact storage model
- Chosen: canonical facts deduplicated globally with separate provenance mentions
- Effect on implementation: store one canonical fact row per unique fact signature and one `fact_mentions` row per supporting source message

### Decision: Seed message style
- Chosen: generate from general model knowledge
- Effect on implementation: write plausible, lightly factual messages without copying a source

### Decision: Offline verification depth
- Chosen: `TestModel`-only offline verification
- Effect on implementation: no golden fixtures are required in version 1

## Remaining Assumptions
None at the plan level.

## Issues
None yet.
