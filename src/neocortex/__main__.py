"""Run the NeoCortex MCP server: python -m neocortex"""

if __name__ == "__main__":
    from neocortex.logging import setup_logging

    setup_logging(service_name="mcp")

    from neocortex.mcp_settings import MCPSettings
    from neocortex.server import create_server

    settings = MCPSettings()
    mcp = create_server(settings)
    mcp.run(transport=settings.transport, host=settings.server_host, port=settings.server_port)
