# Stage 4: Auto-Polling Refresh

**Goal**: Automatically refresh the job list and summary counts on a timer when the Jobs mode is active.
**Dependencies**: Stage 3 (Jobs mode layout and manual refresh working)

---

## Steps

### 1. Add a Textual timer for polling

- File: `src/neocortex/tui/app.py`
- In `__init__`, add:
  ```python
  self._jobs_poll_timer: Timer | None = None
  ```
- Import `Timer` from `textual.timer`.

### 2. Start polling when entering Jobs mode

- In `_show_mode()`, when `mode == "jobs"`:
  ```python
  if self._jobs_poll_timer is None:
      self._jobs_poll_timer = self.set_interval(4, self._poll_jobs, name="jobs_poll")
  ```
- The interval of 4 seconds is a good balance between responsiveness and load.

### 3. Stop polling when leaving Jobs mode

- In `_show_mode()`, when `mode != "jobs"`:
  ```python
  if self._jobs_poll_timer is not None:
      self._jobs_poll_timer.stop()
      self._jobs_poll_timer = None
  ```

### 4. Implement `_poll_jobs()` callback

- This is a thin wrapper that calls `_do_refresh_jobs()`:
  ```python
  def _poll_jobs(self) -> None:
      """Timer callback — trigger an async job refresh."""
      if self._active_panel == "jobs":
          self._do_refresh_jobs()
  ```
- Note: `_do_refresh_jobs()` is a `@work(exclusive=True)` method, so overlapping calls are dropped automatically by Textual. No additional locking needed.

### 5. Visual polling indicator

- In `_do_refresh_jobs()`, briefly update the status label to show polling is happening:
  ```python
  self._set_status("Refreshing jobs...")
  # ... fetch data ...
  self._set_status(f"Last refresh: {datetime.now().strftime('%H:%M:%S')}")
  ```

### 6. Ensure cleanup on app exit

- Override `on_unmount()` or use the existing cleanup path to stop the timer:
  ```python
  def on_unmount(self) -> None:
      if self._jobs_poll_timer is not None:
          self._jobs_poll_timer.stop()
  ```

---

## Verification

- [ ] Manual: enter Jobs mode — job list refreshes automatically every ~4s without user interaction
- [ ] Manual: switch away from Jobs mode — polling stops (verify via log or status label not updating)
- [ ] Manual: switch back to Jobs mode — polling resumes
- [ ] Manual: ingest content while watching Jobs mode — new jobs appear within one poll cycle
- [ ] No errors from overlapping refresh calls (Textual's `exclusive=True` handles this)

---

## Commit

`feat(tui): add auto-polling refresh for jobs mode (4s interval)`
