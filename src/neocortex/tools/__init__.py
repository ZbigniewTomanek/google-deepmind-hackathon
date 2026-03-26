from neocortex.tools.discover import discover
from neocortex.tools.recall import recall
from neocortex.tools.remember import remember


def register_tools(mcp):
    mcp.tool(remember)
    mcp.tool(recall)
    mcp.tool(discover)
