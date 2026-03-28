import pytest
from fastmcp import FastMCP


def test_create_server_returns_fastmcp_instance_with_correct_name(test_server) -> None:
    assert isinstance(test_server, FastMCP)
    assert test_server.name == "NeoCortex"


@pytest.mark.asyncio
async def test_server_registers_expected_tools(test_server) -> None:
    tools = await test_server.list_tools()

    assert [tool.name for tool in tools] == [
        "remember",
        "recall",
        "discover_domains",
        "discover_graphs",
        "discover_ontology",
        "discover_details",
        "browse_nodes",
        "inspect_node",
    ]
