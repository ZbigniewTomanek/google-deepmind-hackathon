from datetime import UTC, datetime
from typing import cast
from unittest.mock import AsyncMock, call

import asyncpg
import pytest

from neocortex.graph_router import GraphRouter
from neocortex.schemas.graph import GraphInfo


def _graph_info(*, graph_id: int, agent_id: str, purpose: str, schema_name: str, is_shared: bool = False) -> GraphInfo:
    return GraphInfo(
        id=graph_id,
        agent_id=agent_id,
        purpose=purpose,
        schema_name=schema_name,
        is_shared=is_shared,
        created_at=datetime.now(UTC),
    )


@pytest.mark.asyncio
async def test_route_store_creates_personal_graph_when_missing() -> None:
    schema_manager = AsyncMock()
    schema_manager.get_graph.return_value = None
    schema_manager.create_graph.return_value = "ncx_alice__personal"
    router = GraphRouter(schema_manager, pool=cast(asyncpg.Pool, object()))

    schema_name = await router.route_store("alice")

    assert schema_name == "ncx_alice__personal"
    schema_manager.get_graph.assert_awaited_once_with(agent_id="alice", purpose="personal")
    schema_manager.create_graph.assert_awaited_once_with(agent_id="alice", purpose="personal")


@pytest.mark.asyncio
async def test_route_store_returns_existing_graph() -> None:
    schema_manager = AsyncMock()
    schema_manager.get_graph.return_value = _graph_info(
        graph_id=1,
        agent_id="alice",
        purpose="personal",
        schema_name="ncx_alice__personal",
    )
    router = GraphRouter(schema_manager, pool=cast(asyncpg.Pool, object()))

    schema_name = await router.route_store("alice")

    assert schema_name == "ncx_alice__personal"
    schema_manager.get_graph.assert_awaited_once_with(agent_id="alice", purpose="personal")
    schema_manager.create_graph.assert_not_called()


@pytest.mark.asyncio
async def test_route_recall_returns_agent_graphs_then_shared_graphs() -> None:
    schema_manager = AsyncMock()
    schema_manager.list_graphs.side_effect = [
        [
            _graph_info(
                graph_id=2,
                agent_id="alice",
                purpose="research",
                schema_name="ncx_alice__research",
            ),
            _graph_info(
                graph_id=1,
                agent_id="alice",
                purpose="personal",
                schema_name="ncx_alice__personal",
            ),
        ],
        [
            _graph_info(
                graph_id=4,
                agent_id="shared",
                purpose="team_notes",
                schema_name="ncx_shared__team_notes",
                is_shared=True,
            ),
            _graph_info(
                graph_id=3,
                agent_id="shared",
                purpose="knowledge",
                schema_name="ncx_shared__knowledge",
                is_shared=True,
            ),
        ],
    ]
    router = GraphRouter(schema_manager, pool=cast(asyncpg.Pool, object()))

    schema_names = await router.route_recall("alice")

    assert schema_names == [
        "ncx_alice__personal",
        "ncx_alice__research",
        "ncx_shared__knowledge",
        "ncx_shared__team_notes",
    ]
    assert schema_manager.list_graphs.await_args_list == [call(agent_id="alice"), call(agent_id="shared")]


@pytest.mark.asyncio
async def test_route_recall_without_shared_graphs_returns_only_agent_graphs() -> None:
    schema_manager = AsyncMock()
    schema_manager.list_graphs.side_effect = [
        [
            _graph_info(
                graph_id=2,
                agent_id="alice",
                purpose="research",
                schema_name="ncx_alice__research",
            ),
            _graph_info(
                graph_id=1,
                agent_id="alice",
                purpose="personal",
                schema_name="ncx_alice__personal",
            ),
        ],
        [],
    ]
    router = GraphRouter(schema_manager, pool=cast(asyncpg.Pool, object()))

    schema_names = await router.route_recall("alice")

    assert schema_names == ["ncx_alice__personal", "ncx_alice__research"]
    assert schema_manager.list_graphs.await_args_list == [call(agent_id="alice"), call(agent_id="shared")]


@pytest.mark.asyncio
async def test_route_discover_uses_recall_routing() -> None:
    schema_manager = AsyncMock()
    schema_manager.list_graphs.side_effect = [
        [_graph_info(graph_id=1, agent_id="alice", purpose="personal", schema_name="ncx_alice__personal")],
        [_graph_info(graph_id=2, agent_id="shared", purpose="knowledge", schema_name="ncx_shared__knowledge")],
    ]
    router = GraphRouter(schema_manager, pool=cast(asyncpg.Pool, object()))

    schema_names = await router.route_discover("alice")

    assert schema_names == ["ncx_alice__personal", "ncx_shared__knowledge"]
