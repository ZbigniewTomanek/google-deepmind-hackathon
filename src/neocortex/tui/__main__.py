"""Run the NeoCortex TUI: python -m neocortex.tui"""

import click

from neocortex.tui.app import NeoCortexApp


@click.command()
@click.option("--url", default="http://localhost:8000", help="MCP server URL")
@click.option("--ingestion-url", default="http://localhost:8001", help="Ingestion API URL (for job monitoring)")
@click.option("--token", default=None, help="Auth token (e.g. tui-dev)")
def main(url: str, ingestion_url: str, token: str | None) -> None:
    """NeoCortex Developer TUI — interact with a running MCP server."""
    app = NeoCortexApp(server_url=url, ingestion_url=ingestion_url, token=token)
    app.run()


if __name__ == "__main__":
    main()
