from fastmcp import FastMCP

from neocortex.tools.discover import (
    discover_details,
    discover_domains,
    discover_graphs,
    discover_ontology,
)
from neocortex.tools.recall import recall
from neocortex.tools.remember import remember


def register_tools(mcp: FastMCP) -> None:
    mcp.tool(remember)
    mcp.tool(recall)
    mcp.tool(discover_domains)
    mcp.tool(discover_graphs)
    mcp.tool(discover_ontology)
    mcp.tool(discover_details)
