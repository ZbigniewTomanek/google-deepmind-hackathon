# Ontology Agent Model Notes

## Current Configuration

- **Model**: Gemini 3 Flash Preview (`google-gla:gemini-3-flash-preview`)
- **Thinking effort**: `medium` (upgraded from `low` in Stage 4)
- **Tool calls limit**: 30 (default)
- **Max new types per episode**: 3 (default)

## Cost Profile

The agentic ontology agent (Stage 3) uses tool calls instead of 0-shot structured
output. This changes the cost profile:

- **Tool calls per episode**: ~3-8 (overview + similarity searches + proposals)
- **Token cost**: ~2-3x vs old 0-shot approach (multiple model round-trips)
- **Ontology step share**: <10% of total extraction cost (librarian dominates)
- **Net impact**: ~5-15% total extraction cost increase for dramatically better type quality

## Tuning Knobs (if quality is insufficient)

1. **Flash + medium thinking** (current) — cheapest, good tool-use sequencing
2. **Flash + high thinking** — better reasoning about type semantics, ~2x ontology cost
3. **Gemini Pro** — strongest semantic judgment, ~5-10x ontology cost (still <50% of total)

## What NOT to Change

- The **extractor** and **librarian** should stay on Flash with low thinking.
  They work within ontology constraints and don't need the same semantic judgment.
- The **tool calls limit** (30) is generous. Typical runs use 3-8. Only increase
  if logs show `UsageLimitExceeded` errors.
- The **max new types** cap (3) is a safety valve. The `propose_type` tool already
  validates against duplicates, so the cap rarely triggers.
