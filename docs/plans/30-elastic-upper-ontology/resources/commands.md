# Commands

Build, test, ingestion, and diagnostic commands for Plan 30.

---

## Service Management

```bash
# Fresh start (wipes DB, recreates schemas)
./scripts/manage.sh stop --all && ./scripts/manage.sh start --fresh

# Normal start
./scripts/manage.sh start

# Status check
./scripts/manage.sh status
```

---

## Corpus Ingestion

All documents ingested via the ingestion API at `localhost:8001`.
Uses the `claude-code-work` dev token.

```bash
# Doc 01: Technical Knowledge (control)
curl -s -X POST http://localhost:8001/ingest/text \
  -H "Authorization: Bearer claude-code-work" \
  -H "Content-Type: application/json" \
  -d '{"text": "We migrated our API gateway from Kong to Envoy Proxy last week. The main driver was gRPC support — Kong'\''s gRPC plugin had connection pooling issues under load. Envoy'\''s configuration is more verbose (YAML-heavy) but the circuit breaker pattern works out of the box. We'\''re using xDS for dynamic configuration via a custom control plane written in Go. Latency dropped from p99 12ms to 8ms after the switch. Next step: integrate with our OpenTelemetry collector for distributed tracing across the mesh.", "source_type": "test_corpus"}'

# Doc 02: Work Context (control)
curl -s -X POST http://localhost:8001/ingest/text \
  -H "Authorization: Bearer claude-code-work" \
  -H "Content-Type: application/json" \
  -d '{"text": "Sprint 14 retrospective notes. The team shipped the payment reconciliation module on time. Jakub handled the Stripe webhook integration, Ola wrote the settlement reports. Main blocker was the staging environment being down for two days — DevOps ticket INFRA-847 took too long. Action items: set up a dedicated QA environment for the payments team, and schedule a knowledge-sharing session on the new event sourcing pattern Marek introduced in the audit trail module. Next sprint starts Monday, planning session at 10:00.", "source_type": "test_corpus"}'

# Doc 03: User Profile (control)
curl -s -X POST http://localhost:8001/ingest/text \
  -H "Authorization: Bearer claude-code-work" \
  -H "Content-Type: application/json" \
  -d '{"text": "Tried intermittent fasting this week — 16:8 window, eating between noon and 8 PM. Energy was good on days 1-3 but crashed on day 4, probably because I also did a hard cycling session that morning. Sleep tracked at 7.2 hours average but REM was low (only 1.1 hours). Going to add a small protein shake at 11 AM as a bridge. Also noticed that magnesium glycinate before bed consistently gives me vivid dreams — three nights in a row now.", "source_type": "test_corpus"}'

# Doc 04: Domain Knowledge (control)
curl -s -X POST http://localhost:8001/ingest/text \
  -H "Authorization: Bearer claude-code-work" \
  -H "Content-Type: application/json" \
  -d '{"text": "Photosynthesis occurs in two stages: light-dependent reactions in the thylakoid membranes and the Calvin cycle in the stroma. The light reactions split water molecules to release oxygen and produce ATP and NADPH. The Calvin cycle then uses these energy carriers to fix CO2 into glucose via the enzyme RuBisCO. C4 plants like maize have evolved a spatial separation mechanism to concentrate CO2 around RuBisCO, reducing photorespiration in hot climates.", "source_type": "test_corpus"}'

# Doc 05: Technical + Personal (cross-domain)
curl -s -X POST http://localhost:8001/ingest/text \
  -H "Authorization: Bearer claude-code-work" \
  -H "Content-Type: application/json" \
  -d '{"text": "Built a personal health dashboard this weekend using Grafana and a Raspberry Pi. It pulls data from my Garmin watch via the API, stores it in InfluxDB, and shows sleep stages, HRV trends, and step counts. The trickiest part was authenticating with Garmin'\''s OAuth2 flow — their token refresh is flaky. Using a cron job to poll every 15 minutes. Noticing that my HRV drops below 30ms on days when I drink coffee after 2 PM. Want to add supplement tracking next — maybe a simple form that writes to the same InfluxDB bucket.", "source_type": "test_corpus"}'

# Doc 06: Work + Domain Knowledge (cross-domain)
curl -s -X POST http://localhost:8001/ingest/text \
  -H "Authorization: Bearer claude-code-work" \
  -H "Content-Type: application/json" \
  -d '{"text": "Attended a conference talk on causal inference in A/B testing. The speaker showed how CUPED (Controlled-experiment Using Pre-Experiment Data) reduces variance by 40-60% compared to naive t-tests. Our experimentation platform at work currently uses basic frequentist tests — going to propose we integrate CUPED in Q3. Shared the paper with Ola and Marek. Also learned about Bayesian adaptive stopping rules which could cut our test durations in half. Need to check if our sample sizes are large enough for the normality assumptions to hold.", "source_type": "test_corpus"}'

# Doc 07: Cinema (novel)
curl -s -X POST http://localhost:8001/ingest/text \
  -H "Authorization: Bearer claude-code-work" \
  -H "Content-Type: application/json" \
  -d '{"text": "Rewatched Tarkovsky'\''s \"Stalker\" last night. The 4-minute tracking shot through the Zone is still mesmerizing — the camera glides over submerged objects while the soundscape shifts from industrial noise to pure silence. Compared to his earlier \"Solaris,\" Stalker is more meditative, less plot-driven. The color grading shift from sepia (outside) to muted greens (inside the Zone) mirrors the psychological transition. Also rewatched the Nolan interview where he cites Tarkovsky as his primary influence on \"Interstellar\"'\''s time dilation sequences.", "source_type": "test_corpus"}'

# Doc 08: Literature / Philosophy (novel)
curl -s -X POST http://localhost:8001/ingest/text \
  -H "Authorization: Bearer claude-code-work" \
  -H "Content-Type: application/json" \
  -d '{"text": "Finished Borges'\'' \"The Library of Babel\" — a story about a universe structured as an infinite hexagonal library containing every possible 410-page book. The philosophical implications are staggering: if every possible text exists, then truth is indistinguishable from noise. Borges anticipates information theory by decades. This connects to Eco'\''s \"The Name of the Rose\" which is partly a response to Borges — the abbey library as a finite, curated version of the infinite one. Also reminds me of Leibniz'\''s characteristica universalis and the dream of encoding all knowledge.", "source_type": "test_corpus"}'

# Doc 09: Music Theory (novel)
curl -s -X POST http://localhost:8001/ingest/text \
  -H "Authorization: Bearer claude-code-work" \
  -H "Content-Type: application/json" \
  -d '{"text": "Practicing jazz piano — working through the ii-V-I progression in all 12 keys. The trick is voice leading: keeping common tones between chords while moving the other voices by step. In C major: Dm7 (D-F-A-C) to G7 (D-F-B-G with altered voicing) to Cmaj7 (C-E-G-B). Modal interchange from parallel minor adds color — borrowing bVII (Bb major) from C Mixolydian over a rock groove. Started transcribing Bill Evans'\'' \"Waltz for Debby\" — his left hand voicings use rootless chord shells that imply the harmony without stating it.", "source_type": "test_corpus"}'

# Doc 10: History / Geopolitics (novel)
curl -s -X POST http://localhost:8001/ingest/text \
  -H "Authorization: Bearer claude-code-work" \
  -H "Content-Type: application/json" \
  -d '{"text": "The fall of Constantinople on May 29, 1453 reshaped Mediterranean trade for centuries. Mehmed II'\''s use of massive bombards (the Orban cannon: 8 meters long, 680kg stone projectiles) made Theodosius'\''s walls — impregnable for 1000 years — obsolete overnight. The immediate aftermath: Venetian and Genoese trading posts lost their Black Sea access, pushing Atlantic exploration. Portuguese navigators like Vasco da Gama sought sea routes to India partly because the Ottoman Empire now controlled overland spice routes. The printing press, arriving in Europe around the same time, helped spread Greek manuscripts that fleeing Byzantine scholars carried west.", "source_type": "test_corpus"}'

# Doc 11: Cooking / Gastronomy (novel)
curl -s -X POST http://localhost:8001/ingest/text \
  -H "Authorization: Bearer claude-code-work" \
  -H "Content-Type: application/json" \
  -d '{"text": "Making authentic Neapolitan pizza requires specific conditions: dough hydration at 65-70%, Tipo 00 flour (Caputo Pizzeria is the gold standard), and a 48-hour cold ferment in the fridge. The oven needs to hit 450C — impossible in home ovens without a pizza steel or Ooni-style portable oven. Sauce is just crushed San Marzano tomatoes (DOP certified, from the slopes of Vesuvius), sea salt, and a drizzle of olive oil. No cooking the sauce. Mozzarella di bufala goes on AFTER the first 60 seconds of baking to prevent burning. The cornicione should be charred in spots — that is the leopard-spotting that marks a proper Neapolitan pie.", "source_type": "test_corpus"}'

# Doc 12: Sports / Athletics (novel)
curl -s -X POST http://localhost:8001/ingest/text \
  -H "Authorization: Bearer claude-code-work" \
  -H "Content-Type: application/json" \
  -d '{"text": "Marathon training follows a periodized structure: base phase (8-12 weeks of easy aerobic mileage at 65-75% max HR), build phase (4-6 weeks adding tempo runs and long intervals), peak phase (3 weeks of race-specific workouts like marathon-pace long runs), and taper (2-3 weeks reducing volume by 40-60%). The Hansons method controversially caps long runs at 16 miles, arguing that cumulative fatigue from high weekly mileage (55-60 miles/week) better simulates race conditions than a single depleting 22-miler. Elite Kenyan runners like Eliud Kipchoge train at altitude in Iten (2400m) where reduced oxygen stimulates EPO production naturally.", "source_type": "test_corpus"}'
```

---

## Diagnostic Queries (Quick)

```bash
# Domain registry
psql "postgresql://neocortex:neocortex@localhost:5432/neocortex" \
  -c "SELECT slug, name, seed, schema_name FROM ontology_domains ORDER BY id;"

# Episode counts per shared schema
for schema in ncx_shared__user_profile ncx_shared__technical_knowledge ncx_shared__work_context ncx_shared__domain_knowledge; do
  echo "=== $schema ==="
  psql "postgresql://neocortex:neocortex@localhost:5432/neocortex" \
    -c "SELECT count(*) AS episodes FROM ${schema}.episode;" 2>/dev/null || echo "  (schema not found)"
done

# Node/type counts per shared schema
for schema in ncx_shared__user_profile ncx_shared__technical_knowledge ncx_shared__work_context ncx_shared__domain_knowledge; do
  echo "=== $schema ==="
  psql "postgresql://neocortex:neocortex@localhost:5432/neocortex" \
    -c "SELECT
          (SELECT count(*) FROM ${schema}.node WHERE NOT forgotten) AS nodes,
          (SELECT count(*) FROM ${schema}.edge) AS edges,
          (SELECT count(*) FROM ${schema}.node_type) AS node_types,
          (SELECT count(*) FROM ${schema}.edge_type) AS edge_types;" 2>/dev/null || echo "  (schema not found)"
done
```

---

## Unit Tests

```bash
# Run domain-related tests
uv run pytest tests/test_domain_classifier.py tests/test_domain_router.py -v

# Run all tests
uv run pytest tests/ -v
```

---

## Job Monitoring

```bash
# Watch extraction jobs complete (poll every 5s)
watch -n 5 'psql "postgresql://neocortex:neocortex@localhost:5432/neocortex" \
  -c "SELECT status, count(*) FROM public.jobs GROUP BY status ORDER BY status;"'

# Check for failed jobs
psql "postgresql://neocortex:neocortex@localhost:5432/neocortex" \
  -c "SELECT id, task_name, status, error, created_at FROM public.jobs WHERE status = '\''failed'\'' ORDER BY created_at DESC LIMIT 10;"
```
