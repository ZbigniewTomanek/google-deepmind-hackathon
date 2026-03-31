# Stage 1: Dependencies

**Goal**: Add multi-provider support to pydantic-ai-slim dependency.
**Dependencies**: None

---

## Steps

1. Update pydantic-ai-slim extras in pyproject.toml
   - File: `pyproject.toml`
   - Line 11: change `"pydantic-ai-slim[google]>=1.72.0"` to `"pydantic-ai-slim[google,openai,anthropic]>=1.72.0"`
   - This installs the provider-specific SDKs (google-genai, openai, anthropic) so
     Pydantic AI can resolve any `provider:model` string at runtime

2. Lock updated dependencies
   - Run: `uv sync`
   - This regenerates `uv.lock` with the new transitive dependencies

---

## Verification

- [ ] `uv sync` completes without errors
- [ ] `uv run python -c "from pydantic_ai.models.openai import OpenAIChatModel; print('openai OK')"` succeeds
- [ ] `uv run python -c "from pydantic_ai.models.anthropic import AnthropicModel; print('anthropic OK')"` succeeds
- [ ] `uv run python -c "from pydantic_ai.models.google import GoogleModel; print('google OK')"` succeeds (existing, should still work)

---

## Commit

`build(deps): add openai and anthropic extras to pydantic-ai-slim`
