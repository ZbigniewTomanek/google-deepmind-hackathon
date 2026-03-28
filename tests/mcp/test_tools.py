import pytest
from fastmcp import Client


@pytest.mark.asyncio
async def test_remember_stores_episode_and_returns_stored_status(test_server) -> None:
    async with Client(test_server) as client:
        result = await client.call_tool(
            "remember",
            {"text": "Alice likes oolong tea.", "context": "preference"},
        )
        recall_result = await client.call_tool("recall", {"query": "oolong"})

    assert result.is_error is False
    assert result.structured_content == {
        "status": "stored",
        "episode_id": 1,
        "message": "Memory stored.",
        "extraction_job_id": None,
    }
    assert recall_result.structured_content["total"] == 1
    assert recall_result.structured_content["results"][0]["content"] == "Alice likes oolong tea."


@pytest.mark.asyncio
async def test_recall_with_empty_repo_returns_empty_results(test_server) -> None:
    async with Client(test_server) as client:
        result = await client.call_tool("recall", {"query": "missing"})

    assert result.is_error is False
    assert result.structured_content == {
        "results": [],
        "total": 0,
        "query": "missing",
    }


@pytest.mark.asyncio
async def test_discover_domains_returns_domains_when_enabled(test_server) -> None:
    async with Client(test_server) as client:
        result = await client.call_tool("discover_domains", {})

    assert result.is_error is False
    data = result.structured_content
    assert data["message"] is None
    assert len(data["domains"]) == 4
    slugs = {d["slug"] for d in data["domains"]}
    assert "user_profile" in slugs
    assert "technical_knowledge" in slugs


@pytest.mark.asyncio
async def test_discover_domains_returns_message_when_disabled(test_server_no_domains) -> None:
    async with Client(test_server_no_domains) as client:
        result = await client.call_tool("discover_domains", {})

    assert result.is_error is False
    data = result.structured_content
    assert data["message"] == "Domain routing is not enabled"
    assert data["domains"] == []


@pytest.mark.asyncio
async def test_discover_graphs_with_empty_repo(test_server) -> None:
    async with Client(test_server) as client:
        result = await client.call_tool("discover_graphs", {})

    assert result.is_error is False
    data = result.structured_content
    assert data["graphs"] == []


@pytest.mark.asyncio
async def test_discover_ontology_with_empty_repo(test_server) -> None:
    async with Client(test_server) as client:
        result = await client.call_tool("discover_ontology", {"graph_name": "ncx_test__personal"})

    assert result.is_error is False
    data = result.structured_content
    assert data["graph_name"] == "ncx_test__personal"
    assert data["node_types"] == []
    assert data["edge_types"] == []


@pytest.mark.asyncio
async def test_discover_details_returns_not_found_for_missing_type(test_server) -> None:
    async with Client(test_server) as client:
        result = await client.call_tool(
            "discover_details",
            {"type_name": "NonExistent", "graph_name": "ncx_test__personal", "kind": "node"},
        )

    assert result.is_error is False
    data = result.structured_content
    assert data["graph_name"] == "ncx_test__personal"
    assert data["type_detail"]["name"] == "NonExistent"
    assert data["type_detail"]["id"] == 0
