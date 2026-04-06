# Test Corpus

Diverse test documents for measuring upper ontology elasticity. Designed to be
ingested via `POST /ingest/text` with `Authorization: Bearer claude-code-work`.

Documents are organized in 3 tiers:
- **Tier 1 (Control)**: Content that fits existing seed domains well
- **Tier 2 (Cross-domain)**: Content spanning multiple domains
- **Tier 3 (Novel)**: Content requiring new domains — the real test

All content is synthetic, concise (~100 words each to keep token cost low).

---

## Tier 1: Existing Domain Control

### Doc 01: Technical Knowledge (control)

**Expected domain**: `technical_knowledge`

```
We migrated our API gateway from Kong to Envoy Proxy last week. The main driver
was gRPC support — Kong's gRPC plugin had connection pooling issues under load.
Envoy's configuration is more verbose (YAML-heavy) but the circuit breaker
pattern works out of the box. We're using xDS for dynamic configuration via a
custom control plane written in Go. Latency dropped from p99 12ms to 8ms after
the switch. Next step: integrate with our OpenTelemetry collector for distributed
tracing across the mesh.
```

### Doc 02: Work Context (control)

**Expected domain**: `work_context`

```
Sprint 14 retrospective notes. The team shipped the payment reconciliation
module on time. Jakub handled the Stripe webhook integration, Ola wrote the
settlement reports. Main blocker was the staging environment being down for two
days — DevOps ticket INFRA-847 took too long. Action items: set up a dedicated
QA environment for the payments team, and schedule a knowledge-sharing session
on the new event sourcing pattern Marek introduced in the audit trail module.
Next sprint starts Monday, planning session at 10:00.
```

### Doc 03: User Profile (control)

**Expected domain**: `user_profile`

```
Tried intermittent fasting this week — 16:8 window, eating between noon and
8 PM. Energy was good on days 1-3 but crashed on day 4, probably because I
also did a hard cycling session that morning. Sleep tracked at 7.2 hours
average but REM was low (only 1.1 hours). Going to add a small protein shake
at 11 AM as a bridge. Also noticed that magnesium glycinate before bed
consistently gives me vivid dreams — three nights in a row now.
```

### Doc 04: Domain Knowledge (control)

**Expected domain**: `domain_knowledge`

```
Photosynthesis occurs in two stages: light-dependent reactions in the thylakoid
membranes and the Calvin cycle in the stroma. The light reactions split water
molecules to release oxygen and produce ATP and NADPH. The Calvin cycle then
uses these energy carriers to fix CO2 into glucose via the enzyme RuBisCO.
C4 plants like maize have evolved a spatial separation mechanism to concentrate
CO2 around RuBisCO, reducing photorespiration in hot climates.
```

---

## Tier 2: Cross-Domain

### Doc 05: Technical + Personal (cross-domain)

**Expected domains**: `technical_knowledge`, `user_profile`

```
Built a personal health dashboard this weekend using Grafana and a Raspberry Pi.
It pulls data from my Garmin watch via the API, stores it in InfluxDB, and
shows sleep stages, HRV trends, and step counts. The trickiest part was
authenticating with Garmin's OAuth2 flow — their token refresh is flaky.
Using a cron job to poll every 15 minutes. Noticing that my HRV drops below
30ms on days when I drink coffee after 2 PM. Want to add supplement tracking
next — maybe a simple form that writes to the same InfluxDB bucket.
```

### Doc 06: Work + Domain Knowledge (cross-domain)

**Expected domains**: `work_context`, `domain_knowledge`

```
Attended a conference talk on causal inference in A/B testing. The speaker
showed how CUPED (Controlled-experiment Using Pre-Experiment Data) reduces
variance by 40-60% compared to naive t-tests. Our experimentation platform
at work currently uses basic frequentist tests — going to propose we
integrate CUPED in Q3. Shared the paper with Ola and Marek. Also learned
about Bayesian adaptive stopping rules which could cut our test durations
in half. Need to check if our sample sizes are large enough for the
normality assumptions to hold.
```

---

## Tier 3: Novel Domains (The Real Test)

### Doc 07: Cinema / Film

**Expected behavior**: Should NOT fit existing domains well. Should trigger
creation of a new domain like `arts_and_culture` or `cinema`.

```
Rewatched Tarkovsky's "Stalker" last night. The 4-minute tracking shot
through the Zone is still mesmerizing — the camera glides over submerged
objects while the soundscape shifts from industrial noise to pure silence.
Compared to his earlier "Solaris," Stalker is more meditative, less
plot-driven. The color grading shift from sepia (outside) to muted greens
(inside the Zone) mirrors the psychological transition. Also rewatched the
Nolan interview where he cites Tarkovsky as his primary influence on
"Interstellar"'s time dilation sequences.
```

### Doc 08: Literature / Philosophy

**Expected behavior**: Should trigger new domain, e.g., `literature` or
`humanities`.

```
Finished Borges' "The Library of Babel" — a story about a universe structured
as an infinite hexagonal library containing every possible 410-page book. The
philosophical implications are staggering: if every possible text exists, then
truth is indistinguishable from noise. Borges anticipates information theory
by decades. This connects to Eco's "The Name of the Rose" which is partly
a response to Borges — the abbey library as a finite, curated version of
the infinite one. Also reminds me of Leibniz's characteristica universalis
and the dream of encoding all knowledge.
```

### Doc 09: Music Theory

**Expected behavior**: Should trigger new domain, e.g., `music` or route
to a broader `arts_and_culture`.

```
Practicing jazz piano — working through the ii-V-I progression in all 12 keys.
The trick is voice leading: keeping common tones between chords while moving
the other voices by step. In C major: Dm7 (D-F-A-C) → G7 (D-F-B-G with
altered voicing) → Cmaj7 (C-E-G-B). Modal interchange from parallel minor
adds color — borrowing bVII (Bb major) from C Mixolydian over a rock groove.
Started transcribing Bill Evans' "Waltz for Debby" — his left hand voicings
use rootless chord shells that imply the harmony without stating it.
```

### Doc 10: History / Geopolitics

**Expected behavior**: Should trigger new domain, e.g., `history` or expand
`domain_knowledge` into sub-domains.

```
The fall of Constantinople on May 29, 1453 reshaped Mediterranean trade for
centuries. Mehmed II's use of massive bombards (the Orban cannon: 8 meters
long, 680kg stone projectiles) made Theodosius's walls — impregnable for
1000 years — obsolete overnight. The immediate aftermath: Venetian and
Genoese trading posts lost their Black Sea access, pushing Atlantic
exploration. Portuguese navigators like Vasco da Gama sought sea routes to
India partly because the Ottoman Empire now controlled overland spice routes.
The printing press, arriving in Europe around the same time, helped spread
Greek manuscripts that fleeing Byzantine scholars carried west.
```

### Doc 11: Cooking / Gastronomy

**Expected behavior**: Might partially match `domain_knowledge` (which has
food types) but should ideally create a more specific `gastronomy` domain.

```
Making authentic Neapolitan pizza requires specific conditions: dough hydration
at 65-70%, Tipo 00 flour (Caputo Pizzeria is the gold standard), and a
48-hour cold ferment in the fridge. The oven needs to hit 450°C — impossible
in home ovens without a pizza steel or Ooni-style portable oven. Sauce is
just crushed San Marzano tomatoes (DOP certified, from the slopes of Vesuvius),
sea salt, and a drizzle of olive oil. No cooking the sauce. Mozzarella di
bufala goes on AFTER the first 60 seconds of baking to prevent burning.
The cornicione should be charred in spots — that's the leopard-spotting
that marks a proper Neapolitan pie.
```

### Doc 12: Sports / Athletics

**Expected behavior**: Could match `user_profile` (if about personal fitness)
but this is about the sport itself, not personal tracking. Should ideally
be a distinct domain or sub-domain.

```
Marathon training follows a periodized structure: base phase (8-12 weeks of
easy aerobic mileage at 65-75% max HR), build phase (4-6 weeks adding tempo
runs and long intervals), peak phase (3 weeks of race-specific workouts like
marathon-pace long runs), and taper (2-3 weeks reducing volume by 40-60%).
The Hansons method controversially caps long runs at 16 miles, arguing that
cumulative fatigue from high weekly mileage (55-60 miles/week) better
simulates race conditions than a single depleting 22-miler. Elite Kenyan
runners like Eliud Kipchoge train at altitude in Iten (2400m) where reduced
oxygen stimulates EPO production naturally.
```

---

## Ingestion Commands

All documents ingested via the ingestion API. See `resources/commands.md` for
the full curl commands.

## Expected Metrics

After ingestion, query the diagnostic SQL in `resources/queries.md` to measure:

1. **Domain routing distribution** — how many episodes per domain
2. **Catch-all absorption** — % of novel content going to domain_knowledge
3. **New domain creation** — any domains beyond the seed 4
4. **Type growth** — new types created per domain per document
5. **Cross-domain routing** — documents routed to multiple domains
