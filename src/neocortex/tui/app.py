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
        if not results:
            self._show_text_result(f"No results found for: {query}")
            return

        lines: list[str] = [f"=== Recall: {total} results for '{query}' ===\n"]

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

                lines.append(
                    f"+-  Node: {center.get('name', name)} "
                    f"[{center.get('type', item_type)}] "
                    f"{'.' * max(1, 50 - len(name) - len(item_type))} "
                    f"score: {score:.3f}{cog_str}"
                )
                if content:
                    short = content[:100] + "..." if len(content) > 100 else content
                    lines.append(f"|  {short}")

                # Build a lookup for neighbor names/types
                neighbor_map = {n.get("id"): n for n in neighbors}
                center_id = center.get("id")

                for i, edge in enumerate(edges):
                    is_last = i == len(edges) - 1
                    branch = "`--" if is_last else "|--"
                    rel_type = edge.get("type", "?")
                    src_id = edge.get("source")
                    tgt_id = edge.get("target")
                    # Determine the "other" node
                    if src_id == center_id:
                        other = neighbor_map.get(tgt_id, {})
                        arrow = f"--[{rel_type}]--> {other.get('name', '?')} [{other.get('type', '?')}]"
                    else:
                        other = neighbor_map.get(src_id, {})
                        arrow = f"<--[{rel_type}]-- {other.get('name', '?')} [{other.get('type', '?')}]"
                    weight = edge.get("weight")
                    weight_str = f" (w={weight:.2f})" if weight is not None else ""
                    lines.append(f"|  {branch} {arrow}{weight_str}")

                if not edges and neighbors:
                    lines.append(f"|  (no direct edges, {len(neighbors)} neighbor(s) at depth {depth})")

                lines.append(f"+{'─' * 58}")
                lines.append("")
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
                lines.append(f"  [{score:.3f}] ({kind}) {name} [{item_type}]: {content}{cog_str}")

        self._show_text_result("\n".join(lines))

    def _show_discover_results(self, result: dict) -> None:
        lines = ["=== Ontology ===\n"]

        node_types = result.get("node_types", [])
        lines.append(f"Node Types ({len(node_types)}):")
        for nt in node_types:
            name = nt.get("name", "?") if isinstance(nt, dict) else str(nt)
            count = nt.get("count", 0) if isinstance(nt, dict) else 0
            desc = nt.get("description", "") if isinstance(nt, dict) else ""
            dots = "." * max(2, 40 - len(name))
            count_str = f"{count} entities"
            line = f"  {name} {dots} {count_str}"
            if desc:
                line += f"  ({desc})"
            lines.append(line)

        edge_types = result.get("edge_types", [])
        lines.append(f"\nEdge Types ({len(edge_types)}):")
        for et in edge_types:
            name = et.get("name", "?") if isinstance(et, dict) else str(et)
            count = et.get("count", 0) if isinstance(et, dict) else 0
            desc = et.get("description", "") if isinstance(et, dict) else ""
            dots = "." * max(2, 40 - len(name))
            count_str = f"{count} relations"
            line = f"  {name} {dots} {count_str}"
            if desc:
                line += f"  ({desc})"
            lines.append(line)

        stats = result.get("stats", {})
        lines.append("\n=== Stats ===")
        lines.append(f"  Nodes:    {stats.get('total_nodes', 0)}")
        lines.append(f"  Edges:    {stats.get('total_edges', 0)}")
        lines.append(f"  Episodes: {stats.get('total_episodes', 0)}")

        # Cognitive stats
        forgotten = stats.get("forgotten_nodes", 0)
        consolidated = stats.get("consolidated_episodes", 0)
        avg_act = stats.get("avg_activation", 0.0)
        if forgotten or consolidated or avg_act:
            lines.append("\n=== Cognitive ===")
            lines.append(f"  Forgotten nodes:        {forgotten}")
            lines.append(f"  Consolidated episodes:  {consolidated}")
            lines.append(f"  Avg activation (nodes): {avg_act:.4f}")

        graphs = result.get("graphs", [])
        if graphs:
            lines.append(f"\n=== Graphs ({len(graphs)}) ===")
            for g in graphs:
                lines.append(f"  - {g}")

        self._show_text_result("\n".join(lines))
