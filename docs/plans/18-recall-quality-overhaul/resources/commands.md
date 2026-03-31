# Build, Test & Run Commands

## Test Commands

```bash
# Run all tests
uv run pytest tests/ -v

# Run scoring tests only (Stages 1-3)
uv run pytest tests/test_scoring.py -v

# Run specific test patterns
uv run pytest tests/test_scoring.py -v -k "dampening"
uv run pytest tests/test_scoring.py -v -k "mmr"
uv run pytest tests/test_scoring.py -v -k "recency"
uv run pytest tests/test_scoring.py -v -k "supersession"

# Run domain tests (Stage 4)
uv run pytest tests/test_domain_classifier.py tests/test_domain_router.py -v

# Run normalization tests (Stage 5)
uv run pytest tests/test_normalization.py -v

# Run all tests with coverage
uv run pytest tests/ -v --cov=src/neocortex --cov-report=term-missing
```

## Service Commands

```bash
# Start with mock DB (no Docker needed)
NEOCORTEX_MOCK_DB=true uv run python -m neocortex

# Start with real DB
docker compose up -d postgres
uv run python -m neocortex

# Start all services
./scripts/launch.sh

# Stop all services
./scripts/launch.sh --stop
```

## Verification Commands

```bash
# Check settings load correctly with new parameters
NEOCORTEX_MOCK_DB=true python -c "
from neocortex.mcp_settings import MCPSettings
s = MCPSettings()
print(f'activation_access_exponent: {s.activation_access_exponent}')
print(f'recall_access_increment_limit: {s.recall_access_increment_limit}')
print(f'recall_mmr_lambda: {s.recall_mmr_lambda}')
print(f'recall_mmr_enabled: {s.recall_mmr_enabled}')
print(f'recall_unconsolidated_episode_boost: {s.recall_unconsolidated_episode_boost}')
print(f'recall_superseded_penalty: {s.recall_superseded_penalty}')
print(f'recall_superseding_boost: {s.recall_superseding_boost}')
print(f'Weights sum: {s.recall_weight_vector + s.recall_weight_text + s.recall_weight_recency + s.recall_weight_activation + s.recall_weight_importance}')
"

# Quick smoke test: recall with mock DB
NEOCORTEX_MOCK_DB=true uv run python -c "
import asyncio
from neocortex.scoring import compute_base_activation, mmr_rerank
from datetime import datetime, UTC

now = datetime.now(UTC)
# Test dampening
print('Dampened (50 accesses):', compute_base_activation(50, now, 0.5, 0.5))
print('Original (50 accesses):', compute_base_activation(50, now, 0.5, 1.0))
print('Dampened (1 access):', compute_base_activation(1, now, 0.5, 0.5))

# Test MMR
results = [
    {'score': 0.9, 'embedding': [1,0,0], 'name': 'A'},
    {'score': 0.8, 'embedding': [0.99,0.1,0], 'name': 'B'},
    {'score': 0.7, 'embedding': [0,1,0], 'name': 'C'},
]
reranked = mmr_rerank(results, lambda_param=0.7)
print('MMR order:', [r['name'] for r in reranked])
"
```

## Log Inspection

```bash
# Check domain routing in action log
grep "domain_classification_result" log/agent_actions.log | tail -5 | python -m json.tool

# Check for activation updates
grep "record_node_access\|record_episode_access" log/agent_actions.log | tail -5

# Check for type validation rejections
grep "invalid_node_type_rejected\|invalid_edge_type_rejected" log/agent_actions.log | tail -5

# Check for supersession edge creation
grep "SUPERSEDES\|CORRECTS" log/agent_actions.log | tail -5
```
