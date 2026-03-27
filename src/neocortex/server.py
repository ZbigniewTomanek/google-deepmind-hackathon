from fastmcp import FastMCP
from starlette.responses import JSONResponse

from neocortex.auth import create_auth
from neocortex.mcp_settings import MCPSettings


def create_server(settings: MCPSettings | None = None) -> FastMCP:
    settings = settings or MCPSettings()
    auth = create_auth(settings)

    mcp = FastMCP(
        name=settings.server_name,
        auth=auth,
        instructions=(
            "NeoCortex is an agent memory system. Use 'remember' to store knowledge, "
            "'recall' to retrieve it, and 'discover' to explore what types of knowledge exist."
        ),
    )

    # Register tools
    from neocortex.tools import register_tools

    register_tools(mcp)

    # Health check
    @mcp.custom_route("/health", methods=["GET"])
    async def health_check(request):
        return JSONResponse({"status": "ok", "version": "0.1.0"})

    return mcp
