# Pydantic AI Provider Reference

## String-based model selection

Pydantic AI accepts `"provider:model-name"` strings directly in `Agent()`.
No provider-specific imports needed.

```python
from pydantic_ai import Agent

agent = Agent("openai:gpt-4o")                      # OpenAI
agent = Agent("anthropic:claude-sonnet-4-5")         # Anthropic
agent = Agent("google-gla:gemini-3-flash-preview")   # Google (GLA)
agent = Agent("google-vertex:gemini-2.5-flash")      # Google (Vertex)
agent = Agent("groq:llama-3.3-70b-versatile")        # Groq
agent = Agent("mistral:mistral-large-latest")        # Mistral
```

## Provider prefixes and env vars

| Provider | Prefix | API key env var | Install extra |
|----------|--------|-----------------|---------------|
| OpenAI | `openai:` | `OPENAI_API_KEY` | `pydantic-ai-slim[openai]` |
| Anthropic | `anthropic:` | `ANTHROPIC_API_KEY` | `pydantic-ai-slim[anthropic]` |
| Google GLA | `google-gla:` | `GOOGLE_API_KEY` | `pydantic-ai-slim[google]` |
| Google Vertex | `google-vertex:` | GCP ADC | `pydantic-ai-slim[google]` |
| Groq | `groq:` | `GROQ_API_KEY` | `pydantic-ai-slim[groq]` |
| Mistral | `mistral:` | `MISTRAL_API_KEY` | `pydantic-ai-slim[mistral]` |
| Bedrock | `bedrock:` | AWS creds | `pydantic-ai-slim[bedrock]` |
| OpenRouter | `openrouter:` | `OPENROUTER_API_KEY` | `pydantic-ai-slim[openrouter]` |

## Out of scope (not using Pydantic AI)

- `embedding_service.py` — uses `google.genai` SDK directly for embeddings
- `media_description.py` — uses `google.genai` SDK directly for multimodal
