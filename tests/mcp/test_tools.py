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
async def test_discover_with_empty_repo_returns_empty_ontology_and_zero_stats(test_server) -> None:
    async with Client(test_server) as client:
        result = await client.call_tool("discover", {})

    assert result.is_error is False
    assert result.structured_content == {
        "node_types": [],
        "edge_types": [],
        "stats": {
            "total_nodes": 0,
            "total_edges": 0,
            "total_episodes": 0,
        },
        "graphs": [],
    }
