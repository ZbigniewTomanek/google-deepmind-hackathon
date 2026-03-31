# Stage 2: Settings

**Goal**: Change model setting defaults to use provider-prefixed strings so the format is self-describing and provider-agnostic.
**Dependencies**: Stage 1 (DONE)

---

## Steps

1. Update default model strings in MCPSettings
   - File: `src/neocortex/mcp_settings.py`
   - Change Pydantic AI model defaults to provider-prefixed format:

   | Field | Old default | New default |
   |-------|-------------|-------------|
   | `ontology_model` (line 111) | `"gemini-3-flash-preview"` | `"google-gla:gemini-3-flash-preview"` |
   | `extractor_model` (line 113) | `"gemini-3-flash-preview"` | `"google-gla:gemini-3-flash-preview"` |
   | `librarian_model` (line 115) | `"gemini-3-flash-preview"` | `"google-gla:gemini-3-flash-preview"` |
   | `domain_classifier_model` (line 121) | `"gemini-3-flash-preview"` | `"google-gla:gemini-3-flash-preview"` |
   - **Note**: `embedding_model` (line 49, `"gemini-embedding-001"`) stays unchanged — it uses
     the raw google-genai SDK, not Pydantic AI, and the provider prefix would be meaningless there.
   - **Note**: `media_description_model` (line 132, `"gemini-3-flash-preview"`) also stays unchanged —
     it uses the raw google-genai SDK directly (not Pydantic AI). Adding a provider prefix would
     create a misleading setting that implies provider-swappability where none exists.

2. Update the docstring for `AgentDomainClassifier.__init__` in `domains/classifier.py`
   - File: `src/neocortex/domains/classifier.py`
   - Line 33: change default parameter `model_name: str = "gemini-3-flash-preview"` to
     `model_name: str = "google-gla:gemini-3-flash-preview"`
   - This is the constructor default — it should match the settings default

3. Update the default in extraction agents
   - File: `src/neocortex/extraction/agents.py`
   - Line 31: change `DEFAULT_MODEL_NAME = "gemini-3-flash-preview"` to
     `DEFAULT_MODEL_NAME = "google-gla:gemini-3-flash-preview"`

4. Update the playground defaults
   - File: `src/pydantic_agents_playground/agents.py`
   - Lines 25-26: remove the separate `MODEL_PROVIDER` constant, change
     `MODEL_NAME = "gemini-3-flash-preview"` to `MODEL_NAME = "google-gla:gemini-3-flash-preview"`

---

## Verification

- [ ] `uv run python -c "from neocortex.mcp_settings import MCPSettings; s = MCPSettings(); assert ':' in s.ontology_model; print('OK:', s.ontology_model)"` prints `OK: google-gla:gemini-3-flash-preview`
- [ ] All Pydantic AI model defaults (`ontology_model`, `extractor_model`, `librarian_model`, `domain_classifier_model`) contain a colon (provider prefix present)
- [ ] `embedding_model` does NOT have a provider prefix (still `gemini-embedding-001`)
- [ ] `media_description_model` does NOT have a provider prefix (still `gemini-3-flash-preview`)

---

## Commit

`refactor(config): use provider-prefixed model strings in settings defaults`
