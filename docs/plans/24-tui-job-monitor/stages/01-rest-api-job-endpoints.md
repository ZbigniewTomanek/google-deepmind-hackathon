# Stage 1: REST API Job Endpoints

**Goal**: Add REST endpoints to the ingestion admin API for listing, inspecting, cancelling, and retrying Procrastinate jobs.
**Dependencies**: None

---

## Steps

### 1. Expose the asyncpg pool on `app.state`

- File: `src/neocortex/ingestion/app.py`
- In the `lifespan` function (line ~62), after `app.state.services_ctx = ctx`, add:
  ```python
  app.state.pool = ctx["pg"].pool if ctx.get("pg") else None  # asyncpg pool for direct queries
  ```
- The pool lives at `ctx["pg"].pool` (where `pg` is a `PostgresService` instance). It is `None` when `NEOCORTEX_MOCK_DB=true`.

### 2. Add job query endpoints to admin routes

- File: `src/neocortex/admin/routes.py`
- Add a new section `# Job monitoring` after the Graph management section.
- Add Pydantic response models:

```python
from datetime import datetime

class JobSummary(BaseModel):
    """Aggregate counts by status."""
    todo: int = 0
    doing: int = 0
    succeeded: int = 0
    failed: int = 0
    cancelled: int = 0
    total: int = 0

class JobInfo(BaseModel):
    """Single job record."""
    id: int
    task_name: str
    status: str
    queue_name: str
    args: dict
    attempts: int
    scheduled_at: datetime | None = None
    # Derived from procrastinate_events (no started_at column on procrastinate_jobs)
    started_at: datetime | None = None
    created_at: datetime | None = None
    finished_at: datetime | None = None
```

### 3. `GET /admin/jobs` — list jobs with optional filters

- Query params: `agent_id: str | None`, `status: str | None`, `task_name: str | None`, `limit: int = 50`, `offset: int = 0`, `all_agents: bool = False`
- Non-admin callers: filter by their own `agent_id` (from `args->>'agent_id'`). Admin callers with `all_agents=True`: no agent filter.
- Auth: use `get_agent_id` from `neocortex.ingestion.auth` (not `require_admin`) so non-admins can see their own jobs. For the `all_agents` flag, check admin status via `request.app.state.permissions.is_admin(agent_id)`.
  ```python
  from neocortex.ingestion.auth import get_agent_id

  @router.get("/admin/jobs")
  async def list_jobs(
      request: Request,
      agent_id: Annotated[str, Depends(get_agent_id)],
      status: str | None = None, ..., all_agents: bool = False,
  ):
      if all_agents:
          permissions = request.app.state.permissions
          if not await permissions.is_admin(agent_id):
              raise HTTPException(403, "Admin required for all_agents view")
          effective_agent_id = None
      else:
          effective_agent_id = agent_id
      ...
  ```
- SQL query against `procrastinate_jobs` table:
  ```sql
  SELECT j.id, j.task_name, j.status, j.queue_name, j.args, j.attempts,
         j.scheduled_at,
         (SELECT at FROM procrastinate_events e WHERE e.job_id = j.id AND e.type = 'started' ORDER BY at DESC LIMIT 1) AS started_at,
         (SELECT MIN(at) FROM procrastinate_events e WHERE e.job_id = j.id AND e.type = 'deferred') AS created_at,
         (SELECT MAX(at) FROM procrastinate_events e WHERE e.job_id = j.id AND e.type IN ('succeeded', 'failed', 'cancelled')) AS finished_at
  FROM procrastinate_jobs j
  WHERE j.queue_name = 'extraction'
    AND ($1::text IS NULL OR j.args->>'agent_id' = $1)
    AND ($2::text IS NULL OR j.status::text = $2)
    AND ($3::text IS NULL OR j.task_name = $3)
  ORDER BY j.id DESC
  LIMIT $4 OFFSET $5
  ```
  **Note:** `procrastinate_jobs` has no `started_at` column — derive it from `procrastinate_events` where `type='started'`.
- Execute via `request.app.state.pool.fetch(...)`.
- Return `list[JobInfo]`.

### 4. `GET /admin/jobs/summary` — aggregate counts

- Same agent_id filtering logic as list.
- SQL:
  ```sql
  SELECT
      count(*) FILTER (WHERE status = 'todo') AS todo,
      count(*) FILTER (WHERE status = 'doing') AS doing,
      count(*) FILTER (WHERE status = 'succeeded') AS succeeded,
      count(*) FILTER (WHERE status = 'failed') AS failed,
      count(*) FILTER (WHERE status = 'cancelled') AS cancelled,
      count(*) AS total
  FROM procrastinate_jobs
  WHERE queue_name = 'extraction'
    AND ($1::text IS NULL OR args->>'agent_id' = $1)
  ```
- Return `JobSummary`.

### 5. `GET /admin/jobs/{job_id}` — single job detail

- Fetch job by ID. Include the full event timeline from `procrastinate_events`.
- Add model:
  ```python
  class JobEvent(BaseModel):
      type: str
      at: datetime

  class JobDetail(JobInfo):
      events: list[JobEvent] = []
  ```
- Return `JobDetail` or 404.

### 6. `DELETE /admin/jobs/{job_id}` — cancel a job

- Only cancels jobs with `status = 'todo'` (queued but not started).
- SQL: `UPDATE procrastinate_jobs SET status = 'cancelled' WHERE id = $1 AND status = 'todo' RETURNING id`
  (Procrastinate's status enum includes `'cancelled'` natively — use it instead of `'failed'` to distinguish user cancellations from actual failures.)
- If no row returned, return 409 (job already running/finished).
- Also insert a `'cancelled'` event into `procrastinate_events`.
- Require admin OR job belongs to the calling agent.

### 7. `POST /admin/jobs/{job_id}/retry` — retry a failed job

- Only retries `status = 'failed'` or `status = 'cancelled'` jobs.
- Read the original job's `task_name` and `args`, then defer a new job with the same parameters.
- Guard: `job_app = request.app.state.services_ctx.get("job_app"); if not job_app: raise HTTPException(501, "Job retry requires extraction to be enabled")`
- The `args` column in `procrastinate_jobs` is the original kwargs dict, so unpack directly:
  ```python
  job_app = request.app.state.services_ctx.get("job_app")
  if not job_app:
      raise HTTPException(501, "Job retry requires extraction to be enabled")
  new_job_id = await job_app.configure_task(task_name).defer_async(**original_args)
  ```
- Return the new job ID.
- Require admin OR job belongs to the calling agent (check `args->>'agent_id'`).

### 8. Handle mock DB mode

- When `NEOCORTEX_MOCK_DB=true`, there's no asyncpg pool. All job endpoints should return 501 with `"Job monitoring requires a real database"`, similar to graph management endpoints.
- Use a reusable helper at the top of the job section (inline, not a dependency):
  ```python
  def _require_pool(request: Request):
      pool = getattr(request.app.state, "pool", None)
      if pool is None:
          raise HTTPException(501, "Job monitoring requires a real database")
      return pool
  ```
- Call `pool = _require_pool(request)` at the start of each job endpoint.

---

## Verification

- [ ] `uv run pytest tests/ -v -k "test_admin"` — existing admin tests still pass
- [ ] `uv run pytest tests/test_admin_jobs.py -v` — new job endpoint tests pass (write basic tests with mock pool or InMemory connector)
- [ ] Manual: start services, ingest text, then `curl http://localhost:8001/admin/jobs/summary -H "Authorization: Bearer admin-dev"` returns counts
- [ ] Manual: `curl http://localhost:8001/admin/jobs -H "Authorization: Bearer admin-dev"` returns job list

---

## Commit

`feat(admin): add REST endpoints for job monitoring (list, summary, detail, cancel, retry)`
