# Stage 3: Contradictions & Corrections

**Goal**: Test explicit contradictions and corrections — can the system handle "X is no longer true, Y is true now"?

**Dependencies**: Stage 2 (graph has both original and updated facts)

---

## Experiment Design

### 3.1 Store a deadline, then change it
```
remember("The project deadline for the Q2 release is April 15, 2026", importance=0.8)
```
Wait, then:
```
remember("The Q2 release deadline has been pushed back from April 15 to May 1, 2026 due to the merge freeze", importance=0.9)
```

### 3.2 Recall the deadline
```
recall("When is the Q2 release deadline?")
recall("project deadline")
```

**Key question**: Does the system return April 15, May 1, or both?
If both: in what order? Does importance/recency affect ranking?

### 3.3 Store an explicit correction
```
remember("CORRECTION: Previously I said the ER engine uses 4-char Metaphone3, but it actually uses 8-char precision. The 4-char information was wrong.", importance=0.9)
```

### 3.4 Recall the corrected fact
```
recall("Metaphone3 precision in the ER engine")
```

**Key question**: Does the explicit "CORRECTION:" framing help the system?

### 3.5 Store a preference reversal
```
remember("The team decided to use RabbitMQ for the event bus", importance=0.7)
```
Then:
```
remember("The team has reversed the RabbitMQ decision and will use Kafka instead, because of partition ordering guarantees", importance=0.8)
```

### 3.6 Recall the preference
```
recall("What message queue does the team use?")
recall("RabbitMQ vs Kafka decision")
```

---

## Verification

- [ ] Deadline recall behavior documented
- [ ] Explicit correction behavior documented
- [ ] Preference reversal behavior documented
- [ ] Pattern identified: does NeoCortex handle any form of contradiction?

---

## Results

### 3.1-3.2 Deadline experiment
[Log results]

### 3.3-3.4 Explicit correction
[Log results]

### 3.5-3.6 Preference reversal
[Log results]

### Analysis
[Is there ANY mechanism that resolves contradictions? Or does the user/agent
have to manually interpret multiple results?]
