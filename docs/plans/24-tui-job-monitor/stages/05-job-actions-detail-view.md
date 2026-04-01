# Stage 5: Job Actions and Detail View

**Goal**: Add job detail drill-down (select a row to see full info), cancel queued jobs, and retry failed jobs from the TUI.
**Dependencies**: Stage 4 (auto-polling working)

---

## Steps

### 1. Handle row selection for job detail drill-down

- File: `src/neocortex/tui/app.py`
- In `on_data_table_row_selected()` (line ~286), add a branch for when `_active_panel == "jobs"`:
  ```python
  if self._active_panel == "jobs":
      row_idx = event.cursor_row
      if 0 <= row_idx < len(self._jobs_data):
          job = self._jobs_data[row_idx]
          self._do_show_job_detail(job["id"])
      return
  ```

### 2. Implement `_do_show_job_detail()` async worker

- Add a `@work(exclusive=True)` method:
  1. Call `self._jobs_client.get_job(job_id)` to fetch full detail with events
  2. Render using `_show_job_detail_text()`
  3. Handle 404 gracefully

### 3. Implement `_show_job_detail_text()` renderer

- Display a Rich `Text` panel showing:
  - **Header**: Job ID, task name, status (color-coded)
  - **Args**: agent_id, episode_ids, target_schema, domain_hint (parsed from args dict)
  - **Timing**: created_at, started_at, finished_at, duration (if both start and finish exist)
  - **Attempts**: current attempts count
  - **Event timeline**: list of events with timestamps
  - **Action hints**: "[c] Cancel  [r] Retry  [b] Back to list"
- Use the `#results-text` Static widget (same as discover detail view pattern)
- Hide the DataTable, show the text panel

### 4. Add action key bindings (context-sensitive)

- Add bindings that are only active when viewing a job detail:
  ```python
  Binding("c", "cancel_job", "Cancel", show=False),
  Binding("x", "retry_job", "Retry", show=False),
  ```
- Store the currently viewed job ID:
  ```python
  self._jobs_selected_id: int | None = None
  ```

### 5. Implement `action_cancel_job()`

- Check `_jobs_selected_id` is set and `_active_panel == "jobs"`
- Call `self._jobs_client.cancel_job(job_id)`
- On success: show confirmation in status, refresh job list
- On 409 (already running/finished): show error in status
- On network error: show error in status

### 6. Implement `action_retry_job()`

- Check `_jobs_selected_id` is set and `_active_panel == "jobs"`
- Call `self._jobs_client.retry_job(job_id)`
- On success: show "New job #{new_id} created" in status, refresh job list
- On error: show error in status

### 7. Add "Back to list" navigation from detail view

- Add a dedicated `action_jobs_back()` method instead of overloading `action_discover_back()`:
  ```python
  def action_jobs_back(self) -> None:
      """Return from job detail to job list."""
      if self._active_panel != "jobs" or self._jobs_selected_id is None:
          return
      self._jobs_selected_id = None
      self._do_refresh_jobs()  # re-show the table
  ```
- Add a key binding that dispatches `b` to the correct action based on mode. Update the existing `action_discover_back()` to remain discover-only. Route the `b` key in a `key_b` handler:
  ```python
  def key_b(self) -> None:
      if self._active_panel == "jobs":
          self.action_jobs_back()
      elif self._active_panel == "discover":
          self.action_discover_back()
  ```
- Remove `Binding("b", "discover_back", ...)` from BINDINGS since `key_b` handles dispatch.

### 8. Visual cues for actionable jobs

- In the job detail view, only show "[c] Cancel" if status is `todo`
- Only show "[x] Retry" if status is `failed` or `cancelled`
- Grey out or hide irrelevant actions

---

## Verification

- [ ] Manual: click a job row in the list → detail panel appears with full info
- [ ] Manual: press `b` from detail → returns to job list
- [ ] Manual: view a `todo` job, press `c` → job cancelled, status updates
- [ ] Manual: view a `failed` job, press `x` → new job created, appears in list
- [ ] Manual: try cancel on a `succeeded` job → error message, no crash
- [ ] Auto-polling continues working after navigating in and out of detail view
- [ ] `uv run pytest tests/ -v` — all tests pass

---

## Commit

`feat(tui): add job detail drill-down with cancel and retry actions`
