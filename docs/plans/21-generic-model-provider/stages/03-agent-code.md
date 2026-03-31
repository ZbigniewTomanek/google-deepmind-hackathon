# Stage 3: Agent Code

**Goal**: Remove all `GoogleModel` imports from agent code and pass model strings directly to Pydantic AI `Agent()`.
**Dependencies**: Stage 2 (DONE)

---

## Steps

### 3a. Extraction agents (`src/neocortex/extraction/agents.py`)

1. Remove the `GoogleModel` import
   - Line 14: delete `from pydantic_ai.models.google import GoogleModel`
   - Keep `from pydantic_ai.models.test import TestModel` — still needed for test mode

2. Update `_build_model()` function (lines 51-57)
   - Instead of `return GoogleModel(config.model_name)`, just return the model string directly.
   - Pydantic AI's `Agent()` accepts either a `Model` object or a `str` — when it receives
     a string like `"google-gla:gemini-3-flash-preview"`, it auto-resolves the correct provider.
   - New implementation:
     ```python
     def _build_model(config: AgentInferenceConfig):
         """Build the LLM model from inference config."""
         if config.use_test_model:
             logger.debug("Using TestModel for extraction agents")
             return TestModel()
         logger.debug("Using model={}", config.model_name)
         return config.model_name
     ```

### 3b. Domain classifier (`src/neocortex/domains/classifier.py`)

1. Remove the `GoogleModel` import
   - Line 13: delete `from pydantic_ai.models.google import GoogleModel`

2. Update `AgentDomainClassifier.__init__()` (line 36)
   - Change `self._model = GoogleModel(model_name)` to `self._model = model_name`
   - The model string is passed directly to `Agent(self._model, ...)` on line 59,
     which already works with strings.

3. Update the class docstring (line 29)
   - Change `"""PydanticAI-based domain classifier using a Gemini model."""`
   - to `"""PydanticAI-based domain classifier."""`

### 3c. Playground agents (`src/pydantic_agents_playground/agents.py`)

1. Remove the `GoogleModel` import
   - Line 7: delete `from pydantic_ai.models.google import GoogleModel`

2. Remove `MODEL_PROVIDER` constant
   - Line 26: delete `MODEL_PROVIDER = "google-gla"` (now embedded in MODEL_NAME)

3. Update `build_model()` function (lines 29-34)
   - Remove `GoogleModel(MODEL_NAME, provider=MODEL_PROVIDER)`, return `MODEL_NAME` directly:
     ```python
     def build_model(use_test_model: bool):
         if use_test_model:
             logger.info("Using TestModel for agent execution")
             return TestModel()
         logger.info("Using model={}", MODEL_NAME)
         return MODEL_NAME
     ```

---

## Verification

- [ ] `grep -r "from pydantic_ai.models.google import GoogleModel" src/` returns NO results
- [ ] `grep -r "GoogleModel" src/` returns NO results (no usage anywhere in src/)
- [ ] `uv run python -c "from neocortex.extraction.agents import _build_model, AgentInferenceConfig; m = _build_model(AgentInferenceConfig()); print(type(m), m)"` prints `<class 'str'> google-gla:gemini-3-flash-preview`
- [ ] `uv run python -c "from neocortex.extraction.agents import _build_model, AgentInferenceConfig; m = _build_model(AgentInferenceConfig(use_test_model=True)); print(type(m))"` prints `<class 'pydantic_ai.models.test.TestModel'>`
- [ ] `uv run pytest tests/ -v` — all existing tests pass

---

## Commit

`refactor(agents): remove GoogleModel imports, use string-based model routing`
