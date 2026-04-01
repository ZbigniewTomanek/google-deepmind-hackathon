"""NeoCortex Developer TUI — Textual-based interface for interacting with the MCP server."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import ClassVar

from rich.text import Text
from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.timer import Timer
from textual.widgets import Button, DataTable, Footer, Header, Input, Label, Select, Static, TextArea

from neocortex.tui.client import JobsClient, NeoCortexClient

MODE_OPTIONS = [("Remember", "remember"), ("Recall", "recall"), ("Discover", "discover"), ("Jobs", "jobs")]

# Consistent color palette for type names
_TYPE_COLORS = [
    "cyan",
    "green",
    "yellow",
    "magenta",
    "blue",
    "red",
    "bright_cyan",
    "bright_green",
    "bright_yellow",
    "bright_magenta",
]


def _color_for_type(type_name: str) -> str:
    """Return a consistent color for a given type name."""
    return _TYPE_COLORS[hash(type_name) % len(_TYPE_COLORS)]


def _importance_bar(value: float, width: int = 10) -> str:
    """Render a mini bar for importance/activation values (0.0-1.0)."""
    filled = round(value * width)
    return "█" * filled + "░" * (width - filled)


@dataclass
class DiscoverLevel:
    """A single level in the discover navigation stack."""

    name: str  # breadcrumb label
    kind: str  # "landing", "domains", "graphs", "ontology", "details", "nodes", "neighborhood"
    data: dict = field(default_factory=dict)  # level-specific data


class NeoCortexApp(App):
    """Developer TUI for NeoCortex MCP server."""

    TITLE = "NeoCortex TUI"
    CSS = """
    #sidebar {
        width: 28;
        background: $surface;
        padding: 1;
        border-right: solid $primary;
    }
    #main-area {
        width: 1fr;
    }
    #input-area {
        height: auto;
        max-height: 24;
        padding: 1;
    }
    #results-area {
        height: 1fr;
        padding: 1;
    }
    #status-label {
        color: $text-muted;
        text-style: italic;
        margin-top: 1;
    }
    #connection-status {
        margin-top: 1;
        color: $success;
    }
    #mode-select {
        margin-bottom: 1;
    }
    .form-label {
        margin-top: 1;
        margin-bottom: 0;
    }
    #remember-area, #recall-area, #discover-area {
        height: auto;
    }
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
    #remember-input {
        height: 6;
    }
    #results-table {
        height: 1fr;
    }
    #results-text {
        height: 1fr;
    }
    #discover-breadcrumb {
        color: $primary;
        text-style: bold;
        margin-bottom: 1;
    }
    #discover-buttons {
        height: auto;
        margin-bottom: 1;
    }
    Button {
        margin-top: 1;
    }
    """
    BINDINGS: ClassVar[list[Binding]] = [
        Binding("r", "switch_mode('remember')", "Remember", show=True),
        Binding("q", "switch_mode('recall')", "Recall", show=True),
        Binding("d", "switch_mode('discover')", "Discover", show=True),
        Binding("j", "switch_mode('jobs')", "Jobs", show=True),
        Binding("b", "discover_back", "Back", show=False),
        Binding("ctrl+q", "quit", "Quit", show=True),
    ]

    def __init__(
        self,
        server_url: str = "http://localhost:8000",
        ingestion_url: str = "http://localhost:8001",
        token: str | None = None,
    ):
        super().__init__()
        self._server_url = server_url
        self._token = token
        self._client = NeoCortexClient(base_url=server_url, token=token)
        self._jobs_client = JobsClient(base_url=ingestion_url, token=token)
        self._active_panel = "remember"
        self._discover_stack: list[DiscoverLevel] = []
        # Rows indexed by table row position for drill-down
        self._discover_row_data: list[dict] = []
        # Jobs mode state
        self._jobs_filter_status: str | None = None  # None = all statuses
        self._jobs_all_agents: bool = False  # toggle for admin view
        self._jobs_data: list[dict] = []  # cached job rows for drill-down
        self._jobs_selected_id: int | None = None
        self._jobs_poll_timer: Timer | None = None

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal():
            with Vertical(id="sidebar"):
                yield Label("Mode", classes="form-label")
                yield Select(MODE_OPTIONS, value="remember", id="mode-select")
                yield Static(f"Server: {self._server_url}", id="connection-status")
                yield Static("Ready", id="status-label")
            with Vertical(id="main-area"):
                with Vertical(id="input-area"):
                    # Remember form
                    with Vertical(id="remember-area"):
                        yield Label("Content to remember:", classes="form-label")
                        yield TextArea(id="remember-input")
                        yield Label("Context (optional):", classes="form-label")
                        yield Input(placeholder="e.g. meeting notes, research", id="remember-context")
                        yield Button("Store Memory", variant="primary", id="remember-btn")
                    # Recall form
                    with Vertical(id="recall-area"):
                        yield Label("Search query:", classes="form-label")
                        yield Input(placeholder="What do you want to recall?", id="recall-query")
                        yield Label("Limit:", classes="form-label")
                        yield Input(value="10", id="recall-limit")
                        yield Button("Search", variant="primary", id="recall-btn")
                    # Discover form — multi-level explorer
                    with Vertical(id="discover-area"):
                        yield Static("Discover", id="discover-breadcrumb")
                        with Horizontal(id="discover-buttons"):
                            yield Button("Domains", variant="primary", id="discover-domains-btn")
                            yield Button("Graphs", variant="primary", id="discover-graphs-btn")
                            yield Button("Browse Nodes", variant="success", id="discover-browse-btn")
                            yield Button("Back", variant="default", id="discover-back-btn")
                    # Jobs mode — status summary + filter buttons
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
                with VerticalScroll(id="results-area"):
                    yield DataTable(id="results-table", cursor_type="row")
                    yield Static("", id="results-text")
        yield Footer()

    def on_mount(self) -> None:
        self._show_mode("remember")
        table = self.query_one("#results-table", DataTable)
        table.display = False
        self.query_one("#discover-back-btn", Button).display = False
        self.query_one("#discover-browse-btn", Button).display = False
        self.query_one("#jobs-area").display = False

    async def on_unmount(self) -> None:
        self._stop_jobs_polling()
        await self._jobs_client.close()

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "mode-select":
            self._show_mode(str(event.value))

    async def action_switch_mode(self, mode: str) -> None:
        self.query_one("#mode-select", Select).value = mode
        self._show_mode(mode)

    def _show_mode(self, mode: str) -> None:
        self._active_panel = mode
        self.query_one("#remember-area").display = mode == "remember"
        self.query_one("#recall-area").display = mode == "recall"
        self.query_one("#discover-area").display = mode == "discover"
        self.query_one("#jobs-area").display = mode == "jobs"
        if mode == "discover":
            self._stop_jobs_polling()
            self._discover_reset()
        elif mode == "jobs":
            # Clear shared widgets from other modes before populating
            table = self.query_one("#results-table", DataTable)
            table.clear(columns=True)
            self.query_one("#results-text", Static).update("")
            table.display = True
            self.query_one("#results-text").display = False
            self._do_refresh_jobs()
            self._start_jobs_polling()
        else:
            self._stop_jobs_polling()
            # Leaving jobs mode — clear jobs state so stale data doesn't linger
            self._jobs_data = []
            self._jobs_selected_id = None
        self._set_status("Ready")

    def _set_status(self, text: str) -> None:
        self.query_one("#status-label", Static).update(text)

    # --- Discover navigation ---

    def _discover_reset(self) -> None:
        """Reset discover to landing (level 0)."""
        self._discover_stack = []
        self._discover_row_data = []
        self._update_discover_ui()
        # Clear results
        table = self.query_one("#results-table", DataTable)
        table.display = False
        result_text = self.query_one("#results-text", Static)
        result_text.display = True
        result_text.update("Select 'Domains' or 'Graphs' to explore the knowledge graph.")

    def _update_discover_ui(self) -> None:
        """Update breadcrumb and button visibility based on stack depth."""
        if not self._discover_stack:
            breadcrumb = "Discover"
        else:
            parts = ["Discover"] + [level.name for level in self._discover_stack]
            breadcrumb = " > ".join(parts)

        self.query_one("#discover-breadcrumb", Static).update(breadcrumb)

        # Show Domains/Graphs buttons only at landing
        at_landing = len(self._discover_stack) == 0
        current_kind = self._discover_stack[-1].kind if self._discover_stack else "landing"
        self.query_one("#discover-domains-btn", Button).display = at_landing
        self.query_one("#discover-graphs-btn", Button).display = at_landing
        self.query_one("#discover-back-btn", Button).display = not at_landing
        # Browse Nodes button visible only at details level (node types)
        self.query_one("#discover-browse-btn", Button).display = (
            current_kind == "details" and self._discover_stack[-1].data.get("kind") == "node"
        )

    def action_discover_back(self) -> None:
        """Pop one level from discover stack (keyboard shortcut 'b')."""
        if self._active_panel != "discover" or not self._discover_stack:
            return
        self._discover_stack.pop()
        self._discover_row_data = []
        self._update_discover_ui()
        if not self._discover_stack:
            self._discover_reset()
        else:
            # Re-render the current top level
            self._render_discover_level(self._discover_stack[-1])

    def _render_discover_level(self, level: DiscoverLevel) -> None:
        """Re-render a discover level from its cached data."""
        if level.kind == "domains":
            self._show_domains_table(level.data.get("domains", []))
        elif level.kind == "graphs":
            self._show_graphs_table(level.data.get("graphs", []))
        elif level.kind == "ontology":
            self._show_ontology_table(level.data)
        elif level.kind == "details":
            self._show_details_text(level.data)
        elif level.kind == "nodes":
            self._show_nodes_table(level.data)
        elif level.kind == "neighborhood":
            self._show_neighborhood(level.data)

    # --- Button handlers ---

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "remember-btn":
            self._do_remember()
        elif event.button.id == "recall-btn":
            self._do_recall()
        elif event.button.id == "discover-domains-btn":
            self._do_discover_domains()
        elif event.button.id == "discover-graphs-btn":
            self._do_discover_graphs()
        elif event.button.id == "discover-back-btn":
            self.action_discover_back()
        elif event.button.id == "discover-browse-btn" and self._discover_stack:
            current = self._discover_stack[-1]
            if current.kind == "details":
                graph_name = current.data.get("graph_name", "")
                type_name = current.data.get("type_name", "")
                if graph_name and type_name:
                    self._do_browse_nodes(graph_name, type_name)
        # Jobs mode buttons
        elif event.button.id == "jobs-filter-all-btn":
            self._jobs_filter_status = None
            self._do_refresh_jobs()
        elif event.button.id == "jobs-filter-todo-btn":
            self._jobs_filter_status = "todo"
            self._do_refresh_jobs()
        elif event.button.id == "jobs-filter-doing-btn":
            self._jobs_filter_status = "doing"
            self._do_refresh_jobs()
        elif event.button.id == "jobs-filter-failed-btn":
            self._jobs_filter_status = "failed"
            self._do_refresh_jobs()
        elif event.button.id == "jobs-filter-cancelled-btn":
            self._jobs_filter_status = "cancelled"
            self._do_refresh_jobs()
        elif event.button.id == "jobs-refresh-btn":
            self._do_refresh_jobs()
        elif event.button.id == "jobs-toggle-agents-btn":
            self._jobs_all_agents = not self._jobs_all_agents
            btn = self.query_one("#jobs-toggle-agents-btn", Button)
            btn.label = "My Jobs" if self._jobs_all_agents else "All Agents"
            self._do_refresh_jobs()

    # --- DataTable row selection for drill-down ---

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        if self._active_panel != "discover" or not self._discover_stack:
            return
        current = self._discover_stack[-1]
        row_idx = event.cursor_row
        if row_idx < 0 or row_idx >= len(self._discover_row_data):
            return

        row = self._discover_row_data[row_idx]

        if current.kind == "graphs":
            # Drill into ontology for this graph
            graph_name = row.get("schema_name", "")
            if graph_name:
                self._do_discover_ontology(graph_name)
        elif current.kind == "ontology":
            # Drill into type details
            type_name = row.get("name", "")
            kind = row.get("kind", "node")
            graph_name = current.data.get("graph_name", "")
            if type_name and graph_name:
                self._do_discover_details(type_name, graph_name, kind)
        elif current.kind == "nodes":
            # Drill into node neighborhood
            node_name = row.get("name", "")
            graph_name = current.data.get("graph_name", "")
            if node_name and graph_name:
                self._do_inspect_node(node_name, graph_name)

    # --- Jobs polling ---

    def _start_jobs_polling(self) -> None:
        """Start the auto-refresh timer for jobs mode."""
        if self._jobs_poll_timer is None:
            self._jobs_poll_timer = self.set_interval(4, self._poll_jobs, name="jobs_poll")

    def _stop_jobs_polling(self) -> None:
        """Stop the auto-refresh timer."""
        if self._jobs_poll_timer is not None:
            self._jobs_poll_timer.stop()
            self._jobs_poll_timer = None

    def _poll_jobs(self) -> None:
        """Timer callback — trigger an async job refresh."""
        if self._active_panel == "jobs":
            self._do_refresh_jobs()

    # --- Jobs ---

    @work(exclusive=True)
    async def _do_refresh_jobs(self) -> None:
        self._set_status("Refreshing jobs...")
        try:
            summary = await self._jobs_client.summary(all_agents=self._jobs_all_agents)
            jobs = await self._jobs_client.list_jobs(
                status=self._jobs_filter_status,
                all_agents=self._jobs_all_agents,
                limit=50,
            )
        except Exception as e:
            self._set_status(f"Error: {type(e).__name__}: {e}")
            self.query_one("#jobs-summary", Static).update(f"Connection error: {e}")
            return

        # Update summary bar
        counts = summary.get("counts", {})
        total = summary.get("total", 0)
        queued = counts.get("todo", 0)
        running = counts.get("doing", 0)
        done = counts.get("succeeded", 0)
        failed = counts.get("failed", 0)
        cancelled = counts.get("cancelled", 0)
        summary_text = (
            f"\u23f3 Queued: {queued}  |  \u25b6 Running: {running}  |  "
            f"\u2713 Done: {done}  |  \u2717 Failed: {failed}  |  "
            f"\u2298 Cancelled: {cancelled}  |  Total: {total}"
        )
        self.query_one("#jobs-summary", Static).update(summary_text)

        self._jobs_data = jobs
        self._show_jobs_table(jobs)
        filter_label = self._jobs_filter_status or "all"
        now = datetime.now().strftime("%H:%M:%S")
        self._set_status(f"Jobs: {len(jobs)} ({filter_label}) — refreshed {now}")

    def _show_jobs_table(self, jobs: list[dict]) -> None:
        """Populate the results DataTable with job rows."""
        table = self.query_one("#results-table", DataTable)
        table.clear(columns=True)
        table.add_columns("ID", "Task", "Status", "Agent", "Episodes", "Target", "Attempts", "Created", "Started")
        table.display = True
        self.query_one("#results-text").display = False

        status_colors = {
            "todo": "cyan",
            "doing": "yellow",
            "succeeded": "green",
            "failed": "red",
            "cancelled": "magenta",
        }

        for job in jobs:
            job_id = str(job.get("id", "?"))
            task = job.get("task_name", "?")
            status = job.get("status", "?")
            attempts = str(job.get("attempts", 0))
            created = job.get("scheduled_at", "")
            started = job.get("started_at", "") or ""

            # Extract agent/episodes/target from args
            args = job.get("args", {})
            agent_id = args.get("agent_id", "")
            episodes = ", ".join(str(e) for e in args.get("episode_ids", [])) if args.get("episode_ids") else ""
            target = args.get("target_schema", "")

            # Truncate timestamps
            if created and len(created) > 19:
                created = created[:19]
            if started and len(started) > 19:
                started = started[:19]

            # Color-code status
            color = status_colors.get(status, "white")
            status_text = Text(status, style=color)

            table.add_row(job_id, task, status_text, agent_id, episodes, target, attempts, created, started)

    # --- Remember ---

    @work(exclusive=True)
    async def _do_remember(self) -> None:
        text = self.query_one("#remember-input", TextArea).text.strip()
        if not text:
            self._set_status("Error: content is empty")
            return
        context = self.query_one("#remember-context", Input).value.strip() or None
        self._set_status("Storing memory...")
        try:
            async with self._client as client:
                result = await client.remember(text, context=context)
            episode_id = result.get("episode_id", "?")
            status = result.get("status", "ok")
            message = result.get("message", "")
            self._show_text_result(
                f"Stored successfully.\n\nEpisode ID: {episode_id}\nStatus: {status}\nMessage: {message}"
            )
            self._set_status("Memory stored")
            self.query_one("#remember-input", TextArea).clear()
            self.query_one("#remember-context", Input).value = ""
        except Exception as e:
            self._show_text_result(f"Error: {e}")
            self._set_status(f"Error: {type(e).__name__}")

    # --- Recall ---

    @work(exclusive=True)
    async def _do_recall(self) -> None:
        query = self.query_one("#recall-query", Input).value.strip()
        if not query:
            self._set_status("Error: query is empty")
            return
        try:
            limit = int(self.query_one("#recall-limit", Input).value.strip())
        except ValueError:
            limit = 10
        self._set_status("Searching...")
        try:
            async with self._client as client:
                result = await client.recall(query, limit=limit)
            results = result.get("results", [])
            total = result.get("total", len(results))
            self._show_recall_results(results, total, query)
            self._set_status(f"Found {total} results")
        except Exception as e:
            self._show_text_result(f"Error: {e}")
            self._set_status(f"Error: {type(e).__name__}")

    # --- Discovery tools ---

    @work(exclusive=True)
    async def _do_discover_domains(self) -> None:
        self._set_status("Fetching domains...")
        try:
            async with self._client as client:
                result = await client.discover_domains()
            domains = result.get("domains", [])
            message = result.get("message")
            level = DiscoverLevel(name="Domains", kind="domains", data={"domains": domains})
            self._discover_stack.append(level)
            self._update_discover_ui()
            if message:
                self._show_text_result(message)
            else:
                self._show_domains_table(domains)
            self._set_status(f"{len(domains)} domain(s)")
        except Exception as e:
            self._show_text_result(f"Error: {e}")
            self._set_status(f"Error: {type(e).__name__}")

    @work(exclusive=True)
    async def _do_discover_graphs(self) -> None:
        self._set_status("Fetching graphs...")
        try:
            async with self._client as client:
                result = await client.discover_graphs()
            graphs = result.get("graphs", [])
            level = DiscoverLevel(name="Graphs", kind="graphs", data={"graphs": graphs})
            self._discover_stack.append(level)
            self._update_discover_ui()
            self._show_graphs_table(graphs)
            self._set_status(f"{len(graphs)} graph(s)")
        except Exception as e:
            self._show_text_result(f"Error: {e}")
            self._set_status(f"Error: {type(e).__name__}")

    @work(exclusive=True)
    async def _do_discover_ontology(self, graph_name: str) -> None:
        self._set_status(f"Fetching ontology for {graph_name}...")
        try:
            async with self._client as client:
                result = await client.discover_ontology(graph_name)
            data = {
                "graph_name": graph_name,
                "node_types": result.get("node_types", []),
                "edge_types": result.get("edge_types", []),
                "stats": result.get("stats", {}),
            }
            level = DiscoverLevel(name=graph_name, kind="ontology", data=data)
            self._discover_stack.append(level)
            self._update_discover_ui()
            self._show_ontology_table(data)
            nt = len(data["node_types"])
            et = len(data["edge_types"])
            self._set_status(f"{nt} node type(s), {et} edge type(s)")
        except Exception as e:
            self._show_text_result(f"Error: {e}")
            self._set_status(f"Error: {type(e).__name__}")

    @work(exclusive=True)
    async def _do_discover_details(self, type_name: str, graph_name: str, kind: str) -> None:
        self._set_status(f"Fetching details for {type_name}...")
        try:
            async with self._client as client:
                result = await client.discover_details(type_name, graph_name, kind)
            detail = result.get("type_detail", {})
            data = {"graph_name": graph_name, "type_name": type_name, "kind": kind, "detail": detail}
            level = DiscoverLevel(name=type_name, kind="details", data=data)
            self._discover_stack.append(level)
            self._update_discover_ui()
            self._show_details_text(data)
            self._set_status(f"Details: {type_name}")
        except Exception as e:
            self._show_text_result(f"Error: {e}")
            self._set_status(f"Error: {type(e).__name__}")

    @work(exclusive=True)
    async def _do_browse_nodes(self, graph_name: str, type_name: str) -> None:
        self._set_status(f"Browsing {type_name} nodes...")
        try:
            async with self._client as client:
                result = await client.browse_nodes(graph_name, type_name=type_name, limit=30)
            nodes = result.get("nodes", [])
            data = {"graph_name": graph_name, "type_name": type_name, "nodes": nodes}
            level = DiscoverLevel(name=f"{type_name} nodes", kind="nodes", data=data)
            self._discover_stack.append(level)
            self._update_discover_ui()
            self._show_nodes_table(data)
            self._set_status(f"{len(nodes)} node(s)")
        except Exception as e:
            self._show_text_result(f"Error: {e}")
            self._set_status(f"Error: {type(e).__name__}")

    @work(exclusive=True)
    async def _do_inspect_node(self, node_name: str, graph_name: str) -> None:
        self._set_status(f"Inspecting {node_name}...")
        try:
            async with self._client as client:
                result = await client.inspect_node(node_name, graph_name)
            data = {
                "graph_name": graph_name,
                "node": result.get("node", {}),
                "edges": result.get("edges", []),
                "neighbor_nodes": result.get("neighbor_nodes", []),
            }
            level = DiscoverLevel(name=node_name, kind="neighborhood", data=data)
            self._discover_stack.append(level)
            self._update_discover_ui()
            self._show_neighborhood(data)
            n_edges = len(data["edges"])
            self._set_status(f"{node_name}: {n_edges} relationship(s)")
        except Exception as e:
            self._show_text_result(f"Error: {e}")
            self._set_status(f"Error: {type(e).__name__}")

    # --- Rendering helpers ---

    def _show_text_result(self, text: str | Text) -> None:
        table = self.query_one("#results-table", DataTable)
        table.display = False
        result_text = self.query_one("#results-text", Static)
        result_text.display = True
        result_text.update(text)

    def _show_table_result(self) -> None:
        """Make the table visible and hide text."""
        table = self.query_one("#results-table", DataTable)
        table.display = True
        result_text = self.query_one("#results-text", Static)
        result_text.display = False

    def _show_domains_table(self, domains: list[dict]) -> None:
        if not domains:
            self._show_text_result("No domains found.")
            return
        table = self.query_one("#results-table", DataTable)
        table.clear(columns=True)
        table.add_columns("Slug", "Name", "Description", "Schema")
        self._discover_row_data = domains
        for d in domains:
            table.add_row(
                d.get("slug", ""),
                d.get("name", ""),
                d.get("description", "")[:60],
                d.get("schema_name", "-"),
            )
        self._show_table_result()

    def _show_graphs_table(self, graphs: list[dict]) -> None:
        if not graphs:
            self._show_text_result("No accessible graphs found.")
            return
        table = self.query_one("#results-table", DataTable)
        table.clear(columns=True)
        table.add_columns("Schema", "Purpose", "Shared", "Nodes", "Edges", "Episodes", "Avg Act.")
        self._discover_row_data = graphs
        for g in graphs:
            stats = g.get("stats", {})
            nodes = stats.get("total_nodes", 0)
            edges = stats.get("total_edges", 0)
            episodes = stats.get("total_episodes", 0)
            avg_act = stats.get("avg_activation", 0.0)
            shared = g.get("is_shared", False)
            table.add_row(
                g.get("schema_name", ""),
                g.get("purpose", ""),
                "shared" if shared else "personal",
                f"{_importance_bar(min(nodes / max(nodes, 1), 1.0), 5)} {nodes}",
                f"{_importance_bar(min(edges / max(edges, 1), 1.0), 5)} {edges}",
                f"{_importance_bar(min(episodes / max(episodes, 1), 1.0), 5)} {episodes}",
                f"{_importance_bar(avg_act, 5)} {avg_act:.2f}",
            )
        self._show_table_result()

    def _show_ontology_table(self, data: dict) -> None:
        node_types = data.get("node_types", [])
        edge_types = data.get("edge_types", [])

        if not node_types and not edge_types:
            self._show_text_result(f"No types found in {data.get('graph_name', '?')}.")
            return

        table = self.query_one("#results-table", DataTable)
        table.clear(columns=True)
        table.add_columns("Kind", "Name", "Description", "Count")

        self._discover_row_data = []
        for nt in node_types:
            name = nt.get("name", "?") if isinstance(nt, dict) else str(nt)
            desc = nt.get("description", "") if isinstance(nt, dict) else ""
            count = nt.get("count", 0) if isinstance(nt, dict) else 0
            table.add_row("● node", name, (desc or "")[:50], str(count))
            self._discover_row_data.append({"name": name, "kind": "node"})

        for et in edge_types:
            name = et.get("name", "?") if isinstance(et, dict) else str(et)
            desc = et.get("description", "") if isinstance(et, dict) else ""
            count = et.get("count", 0) if isinstance(et, dict) else 0
            table.add_row("─ edge", name, (desc or "")[:50], str(count))
            self._discover_row_data.append({"name": name, "kind": "edge"})

        # Show stats below table
        stats = data.get("stats", {})
        if stats:
            stat_text = (
                f"Stats: {stats.get('total_nodes', 0)} nodes, "
                f"{stats.get('total_edges', 0)} edges, "
                f"{stats.get('total_episodes', 0)} episodes"
            )
            self._set_status(stat_text)

        self._show_table_result()

    def _show_details_text(self, data: dict) -> None:
        detail = data.get("detail", {})
        kind = data.get("kind", "node")
        graph = data.get("graph_name", "?")
        name = detail.get("name", "?")
        count = detail.get("count", 0)
        color = _color_for_type(name)

        t = Text()
        # Header panel
        title = f" {kind.title()} Type: {name} "
        t.append(f"╭─{title}{'─' * max(0, 56 - len(title))}╮\n")
        t.append("│  ", style="dim")
        t.append("Graph: ", style="bold")
        t.append(f"{graph:<50}", style="dim cyan")
        t.append("│\n", style="dim")
        t.append("│  ", style="dim")
        t.append("Instances: ", style="bold")
        t.append(f"{count:<45}", style="bright_white")
        t.append("│\n", style="dim")

        desc = detail.get("description")
        if desc:
            t.append("│  ", style="dim")
            t.append("Description: ", style="bold")
            desc_trunc = desc[:43] if len(desc) > 43 else desc
            t.append(f"{desc_trunc:<43}", style="italic")
            t.append("│\n", style="dim")

        t.append(f"│{'':58}│\n", style="dim")

        # Connected types
        connected = detail.get("connected_edge_types", [])
        if connected:
            label = "Connected edge types:" if kind == "node" else "Connected node types:"
            t.append("│  ", style="dim")
            t.append(label, style="bold")
            t.append(f"{'':<{56 - len(label)}}", style="dim")
            t.append("│\n", style="dim")
            for i, ct in enumerate(connected):
                prefix = "└── " if i == len(connected) - 1 else "├── "
                ct_color = _color_for_type(ct)
                t.append("│    ", style="dim")
                t.append(prefix, style="dim")
                t.append(ct, style=ct_color)
                padding = 52 - len(prefix) - len(ct)
                t.append(f"{'':<{max(0, padding)}}", style="dim")
                t.append("│\n", style="dim")
            t.append(f"│{'':58}│\n", style="dim")

        # Samples
        samples = detail.get("sample_names", [])
        if samples:
            t.append("│  ", style="dim")
            t.append("Samples: ", style="bold")
            sample_str = ", ".join(samples[:5])
            if len(sample_str) > 47:
                sample_str = sample_str[:44] + "..."
            t.append(sample_str, style=color)
            padding = 49 - len(sample_str)
            t.append(f"{'':<{max(0, padding)}}", style="dim")
            t.append("│\n", style="dim")
            t.append(f"│{'':58}│\n", style="dim")

        if kind == "node" and count > 0:
            t.append("│  ", style="dim")
            t.append("▸ Press ", style="dim italic")
            t.append("Browse Nodes", style="bold green")
            t.append(" to explore instances", style="dim italic")
            t.append(f"{'':<18}", style="dim")
            t.append("│\n", style="dim")

        t.append(f"╰{'─' * 58}╯\n")

        self._show_text_result(t)

    def _show_nodes_table(self, data: dict) -> None:
        """Render a table of actual node instances."""
        nodes = data.get("nodes", [])
        type_name = data.get("type_name", "")

        if not nodes:
            self._show_text_result(f"No {type_name} nodes found.")
            return

        table = self.query_one("#results-table", DataTable)
        table.clear(columns=True)
        table.add_columns("Name", "Content", "Importance", "Accesses")

        self._discover_row_data = []
        for n in nodes:
            name = n.get("name", "?") if isinstance(n, dict) else str(n)
            content = n.get("content", "") if isinstance(n, dict) else ""
            importance = n.get("importance", 0.5) if isinstance(n, dict) else 0.5
            access_count = n.get("access_count", 0) if isinstance(n, dict) else 0

            content_short = (content or "")[:60]
            if content and len(content) > 60:
                content_short += "..."

            imp_bar = f"{_importance_bar(importance, 8)} {importance:.2f}"

            table.add_row(name, content_short, imp_bar, str(access_count))
            self._discover_row_data.append({"name": name})

        self._show_table_result()

    def _show_neighborhood(self, data: dict) -> None:
        """Render a visual node neighborhood graph."""
        node = data.get("node", {})
        edges = data.get("edges", [])

        node_name = node.get("name", "?")
        node_type = node.get("type_name", "?")
        content = node.get("content", "")
        importance = node.get("importance", 0.5)
        access_count = node.get("access_count", 0)
        color = _color_for_type(node_type)

        t = Text()

        # ── Node info panel ──
        title = f" {node_name} "
        t.append(f"╭─{title}{'─' * max(0, 56 - len(title))}╮\n")

        t.append("│  ", style="dim")
        t.append("Type: ", style="bold")
        t.append(node_type, style=color)
        padding = 52 - len(node_type)
        t.append(f"{'':<{max(0, padding)}}", style="dim")
        t.append("│\n", style="dim")

        if content:
            content_display = content[:52] if len(content) > 52 else content
            t.append("│  ", style="dim")
            t.append("Content: ", style="bold")
            t.append(content_display, style="italic")
            padding = 49 - len(content_display)
            t.append(f"{'':<{max(0, padding)}}", style="dim")
            t.append("│\n", style="dim")

        t.append("│  ", style="dim")
        t.append("Importance: ", style="bold")
        imp_str = f"{_importance_bar(importance, 10)} {importance:.2f}"
        t.append(imp_str)
        access_str = f"   Accesses: {access_count}"
        t.append(access_str)
        padding = 46 - len(imp_str) - len(access_str)
        t.append(f"{'':<{max(0, padding)}}", style="dim")
        t.append("│\n", style="dim")

        t.append(f"╰{'─' * 58}╯\n\n")

        # ── Relationships ──
        if not edges:
            t.append("  No relationships found.\n", style="dim italic")
            self._show_text_result(t)
            return

        n_edges = len(edges)
        overflow = 0
        display_edges = edges
        if n_edges > 20:
            display_edges = edges[:20]
            overflow = n_edges - 20

        t.append(f"  Relationships ({n_edges}):\n\n", style="bold")

        # Separate outgoing and incoming
        outgoing = []
        incoming = []
        for e in display_edges:
            src = e.get("source_name", "?") if isinstance(e, dict) else "?"
            if src == node_name:
                outgoing.append(e)
            else:
                incoming.append(e)

        all_display = outgoing + incoming
        name_pad = len(node_name)

        for i, e in enumerate(all_display):
            is_last = i == len(all_display) - 1
            src_name = e.get("source_name", "?") if isinstance(e, dict) else "?"
            tgt_name = e.get("target_name", "?") if isinstance(e, dict) else "?"
            src_type = e.get("source_type", "?") if isinstance(e, dict) else "?"
            tgt_type = e.get("target_type", "?") if isinstance(e, dict) else "?"
            edge_type = e.get("edge_type", "?") if isinstance(e, dict) else "?"
            weight = e.get("weight", 1.0) if isinstance(e, dict) else 1.0

            et_color = _color_for_type(edge_type)

            if i == 0:
                # First line shows the center node name
                connector = "┌" if not is_last else "─"
                t.append(f"  {'':>{name_pad}}", style="dim")
                t.append(f" {connector}──", style="dim")
            elif is_last:
                t.append(f"  {'':>{name_pad}}", style="dim")
                t.append(" └──", style="dim")
            else:
                t.append(f"  {'':>{name_pad}}", style="dim")
                t.append(" ├──", style="dim")

            if src_name == node_name:
                # Outgoing
                other_name = tgt_name
                other_type = tgt_type
                other_color = _color_for_type(other_type)
                t.append("[", style="dim")
                t.append(edge_type, style=f"bold {et_color}")
                t.append("]", style="dim")
                t.append("──▸ ", style="dim")
                t.append(other_name, style=f"bold {other_color}")
                t.append(f" ({other_type})", style="dim")
            else:
                # Incoming
                other_name = src_name
                other_type = src_type
                other_color = _color_for_type(other_type)
                t.append("[", style="dim")
                t.append(edge_type, style=f"bold {et_color}")
                t.append("]", style="dim")
                t.append("◂── ", style="dim")
                t.append(other_name, style=f"bold {other_color}")
                t.append(f" ({other_type})", style="dim")

            if weight != 1.0:
                t.append(f" w={weight:.2f}", style="dim italic")

            t.append("\n")

            # Vertical connector between rows
            if not is_last:
                t.append(f"  {'':>{name_pad}}", style="dim")
                t.append(" │\n", style="dim")

        # Show center node label
        if all_display:
            t.append("\n")
            t.append("  Center: ", style="dim")
            t.append(node_name, style=f"bold {color}")
            t.append(f" [{node_type}]\n", style="dim")

        if overflow > 0:
            t.append(f"\n  (+{overflow} more relationships)\n", style="dim italic")

        self._show_text_result(t)

    def _show_recall_results(self, results: list, total: int, query: str) -> None:
        if not results:
            self._show_text_result(f"No results found for: {query}")
            return

        t = Text()
        t.append(f"  Recall: {total} results for ", style="bold")
        t.append(f"'{query}'\n\n", style="bold cyan")

        for item in results:
            score = item.get("score", 0)
            kind = item.get("source_kind", "")
            name = item.get("name", "")
            item_type = item.get("item_type", "")
            content = item.get("content", "")
            graph_ctx = item.get("graph_context")

            if kind == "node" and graph_ctx:
                # Node result with graph context — show tree
                center = graph_ctx.get("center_node", {})
                edges = graph_ctx.get("edges", [])
                neighbors = graph_ctx.get("neighbor_nodes", [])
                depth = graph_ctx.get("depth", 0)

                type_color = _color_for_type(item_type)

                # Build cognitive metrics suffix
                cog_parts = []
                act = item.get("activation_score")
                imp = item.get("importance")
                spread = item.get("spreading_bonus")
                if act is not None:
                    cog_parts.append(f"act={act:.2f}")
                if imp is not None:
                    cog_parts.append(f"imp={imp:.2f}")
                if spread is not None and spread > 0:
                    cog_parts.append(f"spread={spread:.2f}")
                cog_str = f"  ({', '.join(cog_parts)})" if cog_parts else ""

                # Header line
                t.append("  ╭─ ", style="dim")
                t.append(center.get("name", name), style=f"bold {type_color}")
                t.append(f" [{center.get('type', item_type)}]", style="dim")
                dots = "·" * max(1, 40 - len(name) - len(item_type))
                t.append(f" {dots} ", style="dim")
                t.append(f"score: {score:.3f}", style="bold")
                t.append(f"{cog_str}\n", style="dim italic")

                if content:
                    short = content[:90] + "..." if len(content) > 90 else content
                    t.append(f"  │  {short}\n", style="dim")

                # Build a lookup for neighbor names/types
                neighbor_map = {n.get("id"): n for n in neighbors}
                center_id = center.get("id")

                for i, edge in enumerate(edges):
                    is_last = i == len(edges) - 1
                    branch = "└──" if is_last else "├──"
                    rel_type = edge.get("type", "?")
                    src_id = edge.get("source")
                    tgt_id = edge.get("target")
                    rel_color = _color_for_type(rel_type)

                    if src_id == center_id:
                        other = neighbor_map.get(tgt_id, {})
                        other_color = _color_for_type(other.get("type", "?"))
                        t.append(f"  │  {branch} ", style="dim")
                        t.append(f"[{rel_type}]", style=f"bold {rel_color}")
                        t.append(" ──▸ ", style="dim")
                        t.append(other.get("name", "?"), style=f"bold {other_color}")
                        t.append(f" [{other.get('type', '?')}]", style="dim")
                    else:
                        other = neighbor_map.get(src_id, {})
                        other_color = _color_for_type(other.get("type", "?"))
                        t.append(f"  │  {branch} ", style="dim")
                        t.append(other.get("name", "?"), style=f"bold {other_color}")
                        t.append(f" [{other.get('type', '?')}]", style="dim")
                        t.append(" ──", style="dim")
                        t.append(f"[{rel_type}]", style=f"bold {rel_color}")
                        t.append(" ──▸", style="dim")

                    weight = edge.get("weight")
                    if weight is not None:
                        t.append(f" (w={weight:.2f})", style="dim italic")
                    t.append("\n")

                if not edges and neighbors:
                    t.append(
                        f"  │  (no direct edges, {len(neighbors)} neighbor(s) at depth {depth})\n",
                        style="dim italic",
                    )

                t.append(f"  ╰{'─' * 58}\n\n")
            else:
                # Episode result or node without graph context — compact line
                if len(content) > 80:
                    content = content[:77] + "..."
                cog_parts = []
                act = item.get("activation_score")
                imp = item.get("importance")
                if act is not None:
                    cog_parts.append(f"act={act:.2f}")
                if imp is not None:
                    cog_parts.append(f"imp={imp:.2f}")
                cog_str = f" ({', '.join(cog_parts)})" if cog_parts else ""

                t.append(f"  [{score:.3f}] ", style="bold")
                t.append(f"({kind}) ", style="dim")
                type_color = _color_for_type(item_type)
                t.append(name, style=f"bold {type_color}")
                t.append(f" [{item_type}]: ", style="dim")
                t.append(content)
                t.append(f"{cog_str}\n", style="dim italic")

        self._show_text_result(t)
