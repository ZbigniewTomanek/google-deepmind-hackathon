# Stage 2: Settings

**Goal**: Change model setting defaults to use provider-prefixed strings so the format is self-describing and provider-agnostic.
**Dependencies**: Stage 1 (DONE)

---

## Steps

1. Update default model strings in MCPSettings
   - File: `src/neocortex/mcp_settings.py`
   - Change all bare model names to provider-prefixed format:

   | Field | Old default | New default |
   |-------|-------------|-------------|
   | `ontology_model` (line 111) | `"gemini-3-flash-preview"` | `"google-gla:gemini-3-flash-preview"` |
   | `extractor_model` (line 113) | `"gemini-3-flash-preview"` | `"google-gla:gemini-3-flash-preview"` |
   | `librarian_model` (line 115) | `"gemini-3-flash-preview"` | `"google-gla:gemini-3-flash-preview"` |
   | `domain_classifier_model` (line 121) | `"gemini-3-flash-preview"` | `"google-gla:gemini-3-flash-preview"` |
   | `media_description_model` (line 132) | `"gemini-3-flash-preview"` | `"google-gla:gemini-3-flash-preview"` |

   - **Note**: `embedding_model` (line 49, `"gemini-embedding-001"`) stays unchanged — it uses
     the raw google-genai SDK, not Pydantic AI, and the provider prefix would be meaningless there.
   - **Note**: `media_description_model` gets the prefix for consistency in the settings file,
     even though the media description service currently strips/ignores the prefix. This makes
     it easy to switch later when/if media description is generalized.

2. Update the docstring for `AgentDomainClassifier.__init__` in `domains/classifier.py`
   - File: `src/neocortex/domains/classifier.py`
   - Line 32: change default parameter `model_name: str = "gemini-3-flash-preview"` to
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
- [ ] All model defaults contain a colon (provider prefix present)
- [ ] `embedding_model` does NOT have a provider prefix (still `gemini-embedding-001`)

---

## Commit

`refactor(config): use provider-prefixed model strings in settings defaults`
