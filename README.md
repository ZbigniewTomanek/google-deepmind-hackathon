# google-deepmind-hackathon

## Pydantic AI BMW Ontology Demo

This repository contains a small teaching demo in `src/pydantic_agents_playground`. It processes 10 fixed BMW 3 Series messages with three Pydantic AI agents: one proposes conservative ontology additions, one extracts ontology-aligned facts, and one normalizes the result for SQLite persistence.

## Run The Demo

Print the current persisted state without running the agents:

```bash
uv run python -m pydantic_agents_playground
```

Offline wiring check with `pydantic_ai.models.test.TestModel`:

```bash
uv run python -m pydantic_agents_playground --use-test-model --reset-db --run-demo
```

By default, the CLI processes 5 seed messages for faster iteration. Override that with `--message-limit 10` when you want the full corpus.

The default SQLite database path is `data/pydantic_agents_playground.sqlite`. To write somewhere else:

```bash
uv run python -m pydantic_agents_playground --use-test-model --reset-db --run-demo --db-path /tmp/bmw-demo.sqlite
```

Live Gemini run with the Google GLA provider:

```bash
export GOOGLE_API_KEY=your_google_api_key
uv run python -m pydantic_agents_playground --reset-db --run-demo
```

The live path uses `google-gla:gemini-3-flash-preview`.

To see the full data flow, including the input message, ontology proposal, extraction result, and normalized persistence payload, run with debug logging:

```bash
PYDANTIC_AGENTS_PLAYGROUND_LOG_LEVEL=DEBUG uv run python -m pydantic_agents_playground --reset-db --run-demo
```

The CLI prints the persisted ontology and canonical facts by default. To recompute first and then print the new state:

```bash
uv run python -m pydantic_agents_playground --reset-db --run-demo
```

## Inspect The Database

After a run, inspect `data/pydantic_agents_playground.sqlite` with any SQLite client or the `sqlite3` CLI. The most useful tables for this demo are:

- `messages`
- `ontology_classes`
- `ontology_class_history`
- `ontology_properties`
- `ontology_property_history`
- `entities`
- `facts`
- `fact_mentions`
- `processing_runs`

Example:

```bash
sqlite3 data/pydantic_agents_playground.sqlite
.tables
SELECT COUNT(*) FROM processing_runs;
SELECT COUNT(*) FROM ontology_classes;
SELECT COUNT(*) FROM facts;
```

## Verification

Mandatory local verification commands for this demo:

```bash
uv run ruff check src
uv run black --check src
uv run python -m pydantic_agents_playground --use-test-model --reset-db --run-demo
poetry run pytest
```

Caveat: the offline `TestModel` path verifies CLI, orchestration, and SQLite wiring, but it does not simulate realistic ontology or fact extraction quality. In the current implementation it processes 5 messages by default and mainly proves the end-to-end flow works without Gemini credentials.
