# Stage 2: TUI Jobs HTTP Client

**Goal**: Add an HTTP client class to the TUI that calls the admin job REST endpoints, and wire it into the app with a `--ingestion-url` CLI flag.
**Dependencies**: Stage 1 (REST endpoints must exist)

---

## Steps

### 1. Add `JobsClient` class

- File: `src/neocortex/tui/client.py`
- Add a new class below `NeoCortexClient`:

```python
import httpx

class JobsClient:
    """HTTP client for the NeoCortex admin job monitoring API.

    Uses a persistent AsyncClient for connection pooling (important since
    the TUI polls every ~4s).
    """

    def __init__(self, base_url: str = "http://localhost:8001", token: str | None = None):
        self._base_url = base_url.rstrip("/")
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        self._client = httpx.AsyncClient(base_url=self._base_url, headers=headers, timeout=10.0)

    async def close(self) -> None:
        """Close the underlying HTTP client. Call on app shutdown."""
        await self._client.aclose()

    async def summary(self, agent_id: str | None = None, all_agents: bool = False) -> dict:
        params = {}
        if agent_id:
            params["agent_id"] = agent_id
        if all_agents:
            params["all_agents"] = "true"
        r = await self._client.get("/admin/jobs/summary", params=params)
        r.raise_for_status()
        return r.json()

    async def list_jobs(self, agent_id: str | None = None, status: str | None = None,
                        limit: int = 50, offset: int = 0, all_agents: bool = False) -> list[dict]:
        params = {"limit": limit, "offset": offset}
        if agent_id:
            params["agent_id"] = agent_id
        if status:
            params["status"] = status
        if all_agents:
            params["all_agents"] = "true"
        r = await self._client.get("/admin/jobs", params=params)
        r.raise_for_status()
        return r.json()

    async def get_job(self, job_id: int) -> dict:
        r = await self._client.get(f"/admin/jobs/{job_id}")
        r.raise_for_status()
        return r.json()

    async def cancel_job(self, job_id: int) -> dict:
        r = await self._client.delete(f"/admin/jobs/{job_id}")
        r.raise_for_status()
        return r.json()

    async def retry_job(self, job_id: int) -> dict:
        r = await self._client.post(f"/admin/jobs/{job_id}/retry")
        r.raise_for_status()
        return r.json()
```

### 2. Add `--ingestion-url` CLI flag

- File: `src/neocortex/tui/__main__.py`
- Add option: `@click.option("--ingestion-url", default="http://localhost:8001", help="Ingestion API URL (for job monitoring)")`
- Pass to `NeoCortexApp`:
  ```python
  app = NeoCortexApp(server_url=url, ingestion_url=ingestion_url, token=token)
  ```

### 3. Wire `JobsClient` into `NeoCortexApp`

- File: `src/neocortex/tui/app.py`
- In `__init__` (line ~126), accept `ingestion_url` param and create `JobsClient`:
  ```python
  def __init__(self, server_url=..., ingestion_url="http://localhost:8001", token=None):
      ...
      self._jobs_client = JobsClient(base_url=ingestion_url, token=token)
  ```
- Import `JobsClient` from `neocortex.tui.client`.

### 4. Verify `httpx` is available

- Check `pyproject.toml` — `httpx` is likely already a transitive dependency (via `fastmcp` or `pydantic-ai`).
- If not, add it: `uv add httpx`.

---

## Verification

- [ ] `uv run python -c "from neocortex.tui.client import JobsClient; print('OK')"` — import works
- [ ] `uv run python -m neocortex.tui --help` — shows `--ingestion-url` option
- [ ] `uv run pytest tests/ -v -k "tui"` — any existing TUI tests still pass

---

## Commit

`feat(tui): add JobsClient HTTP client and --ingestion-url CLI flag`
