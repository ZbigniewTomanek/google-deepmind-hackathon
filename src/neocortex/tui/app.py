"""NeoCortex Developer TUI — Textual-based interface for interacting with the MCP server."""

from __future__ import annotations

from typing import ClassVar

from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Button, DataTable, Footer, Header, Input, Label, Select, Static, TextArea

from neocortex.tui.client import NeoCortexClient

MODE_OPTIONS = [("Remember", "remember"), ("Recall", "recall"), ("Discover", "discover")]


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
        max-height: 16;
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
    #remember-input {
        height: 6;
    }
    #results-table {
        height: 1fr;
    }
    #results-text {
        height: 1fr;
    }
    Button {
        margin-top: 1;
    }
    """
    BINDINGS: ClassVar[list[Binding]] = [
        Binding("r", "switch_mode('remember')", "Remember", show=True),
        Binding("q", "switch_mode('recall')", "Recall", show=True),
        Binding("d", "switch_mode('discover')", "Discover", show=True),
        Binding("ctrl+q", "quit", "Quit", show=True),
    ]

    def __init__(self, server_url: str = "http://localhost:8000", token: str | None = None):
        super().__init__()
        self._server_url = server_url
        self._token = token
        # Each operation opens/closes its own MCP session (stateless by design).
        # This avoids stale-connection issues and keeps the TUI resilient to
        # server restarts between operations.
        self._client = NeoCortexClient(base_url=server_url, token=token)
        self._current_mode = "remember"

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
                    # Discover form
                    with Vertical(id="discover-area"):
                        yield Label("Discover ontology and stats from the knowledge graph.")
                        yield Button("Fetch Ontology", variant="primary", id="discover-btn")
                with VerticalScroll(id="results-area"):
                    yield DataTable(id="results-table")
                    yield Static("", id="results-text")
        yield Footer()

    def on_mount(self) -> None:
        self._show_mode("remember")
        table = self.query_one("#results-table", DataTable)
        table.display = False

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "mode-select":
            self._show_mode(str(event.value))

    async def action_switch_mode(self, mode: str) -> None:
        self.query_one("#mode-select", Select).value = mode
        self._show_mode(mode)

    def _show_mode(self, mode: str) -> None:
        self._current_mode = mode
        self.query_one("#remember-area").display = mode == "remember"
        self.query_one("#recall-area").display = mode == "recall"
        self.query_one("#discover-area").display = mode == "discover"
        self._set_status("Ready")

    def _set_status(self, text: str) -> None:
        self.query_one("#status-label", Static).update(text)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "remember-btn":
            self._do_remember()
        elif event.button.id == "recall-btn":
            self._do_recall()
        elif event.button.id == "discover-btn":
            self._do_discover()

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

    @work(exclusive=True)
    async def _do_discover(self) -> None:
        self._set_status("Fetching ontology...")
        try:
            async with self._client as client:
                result = await client.discover()
            self._show_discover_results(result)
            self._set_status("Ontology loaded")
        except Exception as e:
            self._show_text_result(f"Error: {e}")
            self._set_status(f"Error: {type(e).__name__}")

    def _show_text_result(self, text: str) -> None:
        table = self.query_one("#results-table", DataTable)
        table.display = False
        result_text = self.query_one("#results-text", Static)
        result_text.display = True
        result_text.update(text)

    def _show_recall_results(self, results: list, total: int, query: str) -> None:
        result_text = self.query_one("#results-text", Static)
        result_text.display = False
        table = self.query_one("#results-table", DataTable)
        table.clear(columns=True)
        table.add_columns("Score", "Type", "Kind", "Name", "Content", "Source", "Graph")
        for item in results:
            score = item.get("score", 0)
            if score >= 0.7:
                score_str = f"[green]{score:.3f}[/green]"
            elif score >= 0.3:
                score_str = f"[yellow]{score:.3f}[/yellow]"
            else:
                score_str = f"[red]{score:.3f}[/red]"
            content = item.get("content", "")
            if len(content) > 80:
                content = content[:77] + "..."
            table.add_row(
                score_str,
                item.get("item_type", ""),
                item.get("source_kind", ""),
                item.get("name", ""),
                content,
                item.get("source", "") or "",
                item.get("graph_name", "") or "",
            )
        table.display = True
        if not results:
            self._show_text_result(f"No results found for: {query}")

    def _show_discover_results(self, result: dict) -> None:
        lines = ["=== Ontology ===\n"]

        node_types = result.get("node_types", [])
        lines.append(f"Node Types ({len(node_types)}):")
        for nt in node_types:
            name = nt.get("name", "?") if isinstance(nt, dict) else str(nt)
            count = nt.get("count", 0) if isinstance(nt, dict) else 0
            desc = nt.get("description", "") if isinstance(nt, dict) else ""
            lines.append(f"  - {name} ({count}){': ' + desc if desc else ''}")

        edge_types = result.get("edge_types", [])
        lines.append(f"\nEdge Types ({len(edge_types)}):")
        for et in edge_types:
            name = et.get("name", "?") if isinstance(et, dict) else str(et)
            count = et.get("count", 0) if isinstance(et, dict) else 0
            desc = et.get("description", "") if isinstance(et, dict) else ""
            lines.append(f"  - {name} ({count}){': ' + desc if desc else ''}")

        stats = result.get("stats", {})
        lines.append("\n=== Stats ===")
        lines.append(f"  Nodes:    {stats.get('total_nodes', 0)}")
        lines.append(f"  Edges:    {stats.get('total_edges', 0)}")
        lines.append(f"  Episodes: {stats.get('total_episodes', 0)}")

        graphs = result.get("graphs", [])
        if graphs:
            lines.append(f"\n=== Graphs ({len(graphs)}) ===")
            for g in graphs:
                lines.append(f"  - {g}")

        self._show_text_result("\n".join(lines))
