# Stage 3: TUI Jobs Mode Layout

**Goal**: Add a "Jobs" mode to the TUI with a status summary bar and a scrollable job list table.
**Dependencies**: Stage 2 (JobsClient wired into app)

---

## Steps

### 1. Add "Jobs" to mode options and key bindings

- File: `src/neocortex/tui/app.py`
- Line ~17: Add to `MODE_OPTIONS`:
  ```python
  MODE_OPTIONS = [("Remember", "remember"), ("Recall", "recall"), ("Discover", "discover"), ("Jobs", "jobs")]
  ```
- Line ~118 (`BINDINGS`): Add:
  ```python
  Binding("j", "switch_mode('jobs')", "Jobs", show=True),
  ```

### 2. Add CSS for jobs area

- In the `CSS` string (line ~58), add rules:
  ```css
  #jobs-area {
      height: auto;
      max-height: 6;
  }
  #jobs-summary {
      height: 3;
      padding: 0 1;
  }
  #jobs-filter-row {
      height: auto;
      max-height: 3;
  }
  ```

### 3. Add jobs widgets in `compose()`

- In `compose()` (line ~136), after the `#discover-area` Vertical block (line ~161), add:
  ```python
  with Vertical(id="jobs-area"):
      yield Static("", id="jobs-summary")
      with Horizontal(id="jobs-filter-row"):
          yield Button("All", variant="primary", id="jobs-filter-all-btn")
          yield Button("Queued", variant="default", id="jobs-filter-todo-btn")
          yield Button("Running", variant="warning", id="jobs-filter-doing-btn")
          yield Button("Failed", variant="error", id="jobs-filter-failed-btn")
          yield Button("Cancelled", variant="default", id="jobs-filter-cancelled-btn")
          yield Button("Refresh", variant="success", id="jobs-refresh-btn")
          yield Button("All Agents", variant="default", id="jobs-toggle-agents-btn")
  ```

### 4. Add state variables

- In `__init__` add:
  ```python
  self._jobs_filter_status: str | None = None   # None = all statuses
  self._jobs_all_agents: bool = False            # toggle for admin view
  self._jobs_data: list[dict] = []               # cached job rows for drill-down
  ```

### 5. Update `_show_mode()` to handle jobs

- In `_show_mode()` (line ~188), add:
  ```python
  self.query_one("#jobs-area").display = mode == "jobs"
  if mode == "jobs":
      # Clear shared widgets from other modes before populating
      table = self.query_one("#results-table", DataTable)
      table.clear(columns=True)
      self.query_one("#results-text", Static).update("")
      table.display = True
      self.query_one("#results-text").display = False
      self._do_refresh_jobs()
  else:
      # Leaving jobs mode — clear jobs state so stale data doesn't linger
      self._jobs_data = []
      self._jobs_selected_id = None
  ```

### 6. Hide jobs area on mount

- In `on_mount()` (line ~173), add:
  ```python
  self.query_one("#jobs-area").display = False
  ```

### 7. Implement `_do_refresh_jobs()` async worker

- Add a `@work(exclusive=True)` method that:
  1. Calls `self._jobs_client.summary(all_agents=self._jobs_all_agents)` to get counts
  2. Calls `self._jobs_client.list_jobs(status=self._jobs_filter_status, all_agents=self._jobs_all_agents, limit=50)` to get rows
  3. Updates the `#jobs-summary` Static with formatted counts:
     ```
     ⏳ Queued: 3  |  ▶ Running: 1  |  ✓ Done: 42  |  ✗ Failed: 2  |  ⊘ Cancelled: 1  |  Total: 49
     ```
  4. Calls `_show_jobs_table()` to populate the DataTable
  5. Stores job rows in `self._jobs_data` for drill-down
  6. Handles connection errors gracefully (show error in status)

### 8. Implement `_show_jobs_table()`

- Clear and rebuild the `#results-table` DataTable with columns:
  - **ID** (int), **Task** (str), **Status** (str, color-coded), **Agent** (str, from args), **Episodes** (str, from args), **Target** (str, from args), **Attempts** (int), **Created** (datetime), **Started** (datetime)
- Color-code status: `todo`→cyan, `doing`→yellow, `succeeded`→green, `failed`→red, `cancelled`→magenta
- Use Rich `Text` objects for colored cells

### 9. Wire filter buttons in `on_button_pressed()`

- In `on_button_pressed()` (line ~265), add cases:
  - `jobs-filter-all-btn`: set `_jobs_filter_status = None`, refresh
  - `jobs-filter-todo-btn`: set `_jobs_filter_status = "todo"`, refresh
  - `jobs-filter-doing-btn`: set `_jobs_filter_status = "doing"`, refresh
  - `jobs-filter-failed-btn`: set `_jobs_filter_status = "failed"`, refresh
  - `jobs-filter-cancelled-btn`: set `_jobs_filter_status = "cancelled"`, refresh
  - `jobs-refresh-btn`: refresh
  - `jobs-toggle-agents-btn`: toggle `_jobs_all_agents`, update button label ("All Agents" ↔ "My Jobs"), refresh

---

## Verification

- [ ] `uv run python -m neocortex.tui --help` — runs without import errors
- [ ] Manual: launch TUI with `NEOCORTEX_MOCK_DB=true`, press `j` — Jobs mode shows with summary and empty table (or 501 error message)
- [ ] Manual: with real DB running, press `j` — shows actual job counts and list
- [ ] Filter buttons change the displayed jobs
- [ ] "All Agents" toggle works

---

## Commit

`feat(tui): add Jobs mode with status summary bar and job list table`
