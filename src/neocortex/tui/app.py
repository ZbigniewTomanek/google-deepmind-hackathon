"""NeoCortex Developer TUI — Textual-based interface for interacting with the MCP server."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import ClassVar

from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Button, DataTable, Footer, Header, Input, Label, Select, Static, TextArea

from neocortex.tui.client import NeoCortexClient

MODE_OPTIONS = [("Remember", "remember"), ("Recall", "recall"), ("Discover", "discover")]


@dataclass
class DiscoverLevel:
    """A single level in the discover navigation stack."""

    name: str  # breadcrumb label
    kind: str  # "landing", "domains", "graphs", "ontology", "details"
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
        Binding("b", "discover_back", "Back", show=False),
        Binding("ctrl+q", "quit", "Quit", show=True),
    ]

    def __init__(self, server_url: str = "http://localhost:8000", token: str | None = None):
        super().__init__()
        self._server_url = server_url
        self._token = token
        self._client = NeoCortexClient(base_url=server_url, token=token)
        self._active_panel = "remember"
        self._discover_stack: list[DiscoverLevel] = []
        # Rows indexed by table row position for drill-down
        self._discover_row_data: list[dict] = []

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
                            yield Button("Back", variant="default", id="discover-back-btn")
                with VerticalScroll(id="results-area"):
                    yield DataTable(id="results-table")
                    yield Static("", id="results-text")
        yield Footer()

    def on_mount(self) -> None:
        self._show_mode("remember")
        table = self.query_one("#results-table", DataTable)
        table.display = False
        self.query_one("#discover-back-btn", Button).display = False

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
        if mode == "discover":
            self._discover_reset()
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
        self.query_one("#discover-domains-btn", Button).display = at_landing
        self.query_one("#discover-graphs-btn", Button).display = at_landing
        self.query_one("#discover-back-btn", Button).display = not at_landing

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

    # --- Rendering helpers ---

    def _show_text_result(self, text: str) -> None:
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
        table.add_columns("Schema", "Purpose", "Shared", "Nodes", "Edges", "Episodes")
        self._discover_row_data = graphs
        for g in graphs:
            stats = g.get("stats", {})
            table.add_row(
                g.get("schema_name", ""),
                g.get("purpose", ""),
                "yes" if g.get("is_shared") else "no",
                str(stats.get("total_nodes", 0)),
                str(stats.get("total_edges", 0)),
                str(stats.get("total_episodes", 0)),
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
            table.add_row("node", name, (desc or "")[:50], str(count))
            self._discover_row_data.append({"name": name, "kind": "node"})

        for et in edge_types:
            name = et.get("name", "?") if isinstance(et, dict) else str(et)
            desc = et.get("description", "") if isinstance(et, dict) else ""
            count = et.get("count", 0) if isinstance(et, dict) else 0
            table.add_row("edge", name, (desc or "")[:50], str(count))
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

        lines = [
            f"=== {kind.title()} Type: {detail.get('name', '?')} ===",
            f"Graph: {graph}",
            f"ID: {detail.get('id', '?')}",
            f"Count: {detail.get('count', 0)}",
            "",
        ]

        desc = detail.get("description")
        if desc:
            lines.append(f"Description: {desc}")
            lines.append("")

        connected = detail.get("connected_edge_types", [])
        if connected:
            lines.append(f"Connected edge types ({len(connected)}):")
            for et in connected:
                lines.append(f"  - {et}")
            lines.append("")

        samples = detail.get("sample_names", [])
        if samples:
            lines.append(f"Sample names ({len(samples)}):")
            for s in samples:
                lines.append(f"  - {s}")

        self._show_text_result("\n".join(lines))

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
