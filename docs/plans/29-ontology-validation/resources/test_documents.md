# Test Documents

Test corpus for ontology alignment validation. Each document is designed to exercise
specific domains and edge cases. Documents are ingested via `POST /ingest/text`
with `Authorization: Bearer claude-code-work`.

All content is synthetic but realistic -- modeled after the patterns that caused
problems in Plan 28 (weekly notes, health protocols, car knowledge, etc.).

---

## Document 1: Weekly Note (user_profile + domain_knowledge)

**Expected domains**: user_profile, domain_knowledge
**Expected types**: Person, Location, FoodItem, Activity, Emotion, Trip

```
Weekly Note — March 24-30

Had a great week overall. Monday was productive — finished the kitchen renovation
planning with Anna. We decided on quartz countertops from IKEA, estimated cost
around 3200 EUR. The contractor Jan starts demolition on April 15.

Tuesday I tried a new recipe: shakshuka with feta and za'atar. Used the cast iron
skillet. Turned out really well — the key is letting the tomato sauce reduce for
at least 20 minutes before adding eggs.

Wednesday morning run — 7.2km in 38 minutes along the river trail. Felt strong,
no knee pain for the first time in weeks. The new Asics Gel-Kayano shoes might be
making a difference.

Thursday was stressful at work (see work notes). Compensated with a long evening
walk and meditation session. Sleep quality was poor — woke up twice, total 6.1 hours.

Weekend trip to Kraków with Marta. Visited Wawel Castle and the Cloth Hall. Had
amazing pierogi at a place called Przystanek Pierogarnia near the main square.
The obwarzanki from street vendors were surprisingly good too.

Mood: generally positive, dip on Thursday. Energy levels: 7/10 average.
```

---

## Document 2: Health Protocol (user_profile)

**Expected domains**: user_profile
**Expected types**: Substance, Symptom, Protocol, Metric, BodyPart, Person

```
Morning Supplement Stack — Spring 2026 Update

After blood work results from Dr. Kowalski (March 15), adjusted the protocol:

1. Vitamin D3 — increased from 2000 IU to 4000 IU daily. Serum level was 28 ng/mL
   (target: 40-60). Taking with breakfast (fat-soluble, needs dietary fat for absorption).

2. Magnesium Glycinate — 400mg before bed. Helps with sleep quality and muscle
   recovery. Switched from citrate form because it was causing loose stools.

3. Omega-3 (EPA/DHA) — 2g daily, split morning/evening. Triglycerides were
   borderline at 148 mg/dL. Nordic Naturals brand, kept in fridge.

4. Creatine Monohydrate — 5g daily in morning smoothie. For cognitive performance
   and gym recovery. No loading phase needed.

5. Zinc Picolinate — 30mg with lunch. Was slightly deficient. Don't take with
   coffee or calcium (absorption interference).

Dropped: Ashwagandha — was causing afternoon drowsiness. Melatonin — sleep is
better with magnesium alone.

Blood work recheck scheduled for June 20 to verify D3 and triglyceride improvements.
Side effects to monitor: magnesium can cause drowsiness if dose too high. Zinc on
empty stomach causes nausea.
```

---

## Document 3: Car Knowledge (domain_knowledge)

**Expected domains**: domain_knowledge
**Expected types**: Vehicle, Component, Specification, Brand, Service

```
BMW F31 320d Touring — Maintenance Notes

Vehicle: 2016 BMW 320d Touring (F31), 2.0L diesel, 190hp, 8-speed ZF auto.
Current mileage: 142,000 km. VIN: WBAXXXXXXXX.

Timing chain: B47 engine uses a chain, not belt — no scheduled replacement, but
listen for rattle on cold start (chain stretch symptom, common above 150k km).
Replacement cost if needed: ~2500 EUR at independent shop.

Oil: BMW LL-04 spec, 5W-30. Castrol Edge Professional recommended. Capacity:
5.2L with filter change. Change interval: 15,000 km or 12 months (I do 10,000 km
to be safe). Last change at 139,000 km (January 2026).

Brake pads: Front pads replaced at 128,000 km. Rear pads still at ~4mm — should
last another 15-20k km. Using Brembo P06 076 pads. Sensor wire needs replacement
with pads (one-time use).

DPF (Diesel Particulate Filter): Regeneration cycle every ~400-600 km. If mostly
city driving, do a 30-min highway run monthly to force active regen. Warning light
means manual regen needed at dealer (costs ~150 EUR). DPF replacement: ~2000 EUR.

Known issues at this mileage:
- Swirl flap actuator can fail (P2015 code) — replacement ~400 EUR
- Rear air springs (if equipped) leak around 140-160k km — ~300 EUR per side
- EGR valve carbon buildup — clean every 60k km, or replace ~600 EUR
```

---

## Document 4: Technical Architecture (technical_knowledge)

**Expected domains**: technical_knowledge
**Expected types**: Tool, Component, Concept, ArchitecturePattern, Infrastructure

```
Event Sourcing with PostgreSQL — Architecture Decision Record

Context: Evaluating event sourcing as the persistence pattern for the ingestion
pipeline. Currently using simple INSERT-based storage with no event log.

Decision: Adopt event sourcing for episode lifecycle only. Not for the full
knowledge graph (too complex, poor query performance for graph traversals).

Architecture:
- Event store: PostgreSQL table with JSONB payload column. Partitioned by month.
- Event types: EpisodeCreated, EpisodeEmbedded, ExtractionStarted, ExtractionCompleted,
  ExtractionFailed, EpisodeConsolidated.
- Projection: Materialized view for current episode state (latest event per episode_id).
- Snapshots: Not needed initially — event count per episode is small (5-8 events max).

Technology choices:
- PostgreSQL over Kafka: We're single-node, <1000 events/day. Kafka adds operational
  complexity we don't need. PG advisory locks handle concurrency.
- JSONB over normalized columns: Event schemas will evolve. JSONB with a version
  field avoids migrations per event type.
- Procrastinate (job queue) stays: Events trigger jobs, not replace them. The job
  system handles retries, dead letters, and observability.

Risks:
- Event replay performance degrades with partition count. Mitigate: yearly archive
  of old partitions.
- Schema evolution of event payloads. Mitigate: version field + upcasting functions.

Related: Martin Fowler's event sourcing guide, Greg Young's CQRS/ES talks,
Marten library (similar approach in .NET with PG).
```

---

## Document 5: Work Context (work_context)

**Expected domains**: work_context
**Expected types**: Project, Task, Person, Organization, Ticket, Presentation

```
Sprint Review Notes — March 28, 2026

Team: Data Platform (6 engineers + PM Sarah + TL Marcus)
Sprint: 2026-Q1-S6 (March 18 - March 28)

Completed:
1. PLAT-1234: Migration runner v2 — automatic rollback on failure. Took 5 story
   points. Marcus did the implementation, I reviewed. Good test coverage.
2. PLAT-1245: Dashboard latency widget — P95 latency chart for ingestion pipeline.
   Connected to Grafana. 3 story points. Julia's first solo feature — clean work.
3. PLAT-1251: Fix connection pool exhaustion under load — was hitting 100 connections
   during batch ingestion. Increased pool to 50, added connection timeout of 30s.
   Root cause: long-running transactions in extraction pipeline holding connections.
   2 story points.

Carried over:
- PLAT-1260: Schema versioning for graph migrations — blocked on decisions about
  backward compatibility. Need architecture review with CTO next week.
- PLAT-1248: Embedding service failover — waiting for GCP quota increase.

Demo: Showed the migration runner rollback to stakeholders. Good reception.
Product manager Tomek asked about self-service schema creation — added to backlog
as PLAT-1270.

Retro highlights:
- Positive: PR review turnaround improved (avg 4h → 2h)
- Action item: Set up automated performance regression tests (assigned to me,
  due April 11)

Next sprint planning: Monday March 31, 10:00 with Sarah.
```

---

## Document 6: Mixed/Ambiguous Content (cross-domain)

**Expected domains**: user_profile + technical_knowledge (ambiguous boundary)
**Expected types**: Should reuse existing types, not create new ones

```
Setting Up the Home Lab — Weekend Project

Finally configured the Mac Mini M2 as a home server. Running:
- Proxmox VE as hypervisor (bare metal, 16GB RAM, 512GB NVMe)
- Home Assistant in a VM for smart home automation
- Pi-hole in LXC container for DNS-level ad blocking
- Tailscale mesh VPN for remote access

The tricky part was getting Proxmox networking right — had to set up a bridge
interface (vmbr0) and configure DHCP reservation on the UniFi router for stable IP.

Also set up automated backups: Proxmox vzdump runs nightly at 3 AM, stores to
a Synology NAS via NFS. Retention: 7 daily + 4 weekly. Total backup size ~40GB.

Smart home automations worth noting:
- Motion sensor in hallway triggers lights (Hue) between sunset and 11 PM
- Temperature sensor in bedroom adjusts AC setpoint via Tado
- Door sensor sends notification if front door open > 5 minutes

Power consumption of the whole setup: ~35W idle, ~60W under load. Monthly cost
at current electricity rate (0.28 EUR/kWh): about 7-12 EUR. Worth it.

Next: want to add Jellyfin for media streaming and Immich for photo backup.
```

---

## Document 7: Adversarial — Entity Names That Could Leak Into Types

**Purpose**: Test instance-level type detection. Names like "Asset Manager Pro",
"Event Horizon", "Activity Tracker" could trick the LLM into creating types like
`AssetManagerPro` or `EventHorizon`.

```
App Reviews — Tools I Use Daily

Activity Tracker Pro — best fitness app I've found. Tracks runs, cycling, and
gym sessions. The GPS accuracy is better than Strava. Cost: 4.99 EUR/month.
Integrates with Apple Health and exports to CSV.

Asset Manager Pro — using this for tracking household inventory and warranties.
Registered the new dishwasher (Bosch SMS46GI55E, purchased March 2026, warranty
until March 2028). Also tracking the road bike (Canyon Endurace CF 7, 2024 model).

Dream Journal — simple app for recording dreams. Voice-to-text in the morning
works surprisingly well. Have 47 entries so far. Most common themes: flying,
being late, work presentations.

Location Scout — photography planning app. Shows golden hour times, sun position,
and lets you pin locations. Saved 12 spots around Warsaw for spring shoots.

Insight Timer — meditation app with free content. Using the 10-minute morning
mindfulness course. Day 34 of the streak.
```

---

## Document 8: Adversarial — Technical Jargon That Could Create Garbage Types

**Purpose**: Test that the ontology agent doesn't create overly specific types
for technical concepts that belong under existing types like `Concept` or `Tool`.

```
Debugging the Memory Leak — Postmortem

Service: ingestion-worker (Python 3.12, FastAPI + asyncpg)
Incident: OOM kill at 2 AM on March 20, pod restarted 3 times before alert fired.

Root cause: The EmbeddingBatchProcessor was accumulating numpy arrays in a list
without clearing between batches. Each batch added ~50MB. After processing 200
episodes overnight, memory hit 12GB and triggered the OOM killer.

Fix: Added explicit `del` + `gc.collect()` after each batch. Also reduced batch
size from 100 to 25 episodes. Memory now stable at ~800MB under sustained load.

Investigation tools used:
- py-spy for CPU profiling (attached to running container)
- memray for memory profiling (ran locally with replay data)
- kubectl top pods for real-time memory monitoring
- Grafana dashboard (grafana.internal/d/api-latency) for correlation with latency

Lessons:
- Python's garbage collector doesn't handle numpy array cycles well
- asyncpg connection objects hold references to large result sets
- The pod memory limit (4GB) was too low for batch processing — increased to 8GB
- Need memory profiling in CI (tracked as PLAT-1275)

Prevention: Added a memory watchdog that logs warning at 70% limit and kills
gracefully at 85%. Also added batch-level memory logging to track growth.
```

---

## Document 9: Volume Filler — Short Personal Notes (5 entries)

**Purpose**: Bulk content for volume testing. Ingest each as separate episodes.

### 9a
```
Dentist appointment with Dr. Nowak on April 8 at 14:30. Need to ask about the
wisdom tooth — it's been causing occasional pain on the lower right side.
```

### 9b
```
Book finished: "Thinking in Systems" by Donella Meadows. Key takeaway: feedback
loops are everywhere, and delays in feedback are the main source of system
instability. Recommended by Marcus at work. Rating: 9/10.
```

### 9c
```
Grocery list for the week: salmon fillets, avocados, sweet potatoes, Greek yogurt,
almonds, spinach, eggs, oat milk, frozen berries, dark chocolate (85%+).
Budget: ~180 PLN.
```

### 9d
```
Guitar practice log — March 26. Worked on fingerpicking pattern for "Blackbird"
by The Beatles. Getting smoother on the transitions between G and A minor.
Practice time: 35 minutes. Need to work on the descending run in the bridge.
```

### 9e
```
Apartment maintenance: replaced the kitchen faucet aerator (was calcified, water
pressure was dropping). Bought a Neoperl M24 from Castorama for 12 PLN. Took
5 minutes with an adjustable wrench. Water flow much better now.
```
