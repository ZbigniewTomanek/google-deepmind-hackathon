import pytest


@pytest.mark.asyncio
async def test_seed_node_types_exist(graph_service):
    types = await graph_service.list_node_types()
    names = {t.name for t in types}
    assert "Concept" in names
    assert "Person" in names


@pytest.mark.asyncio
async def test_seed_edge_types_exist(graph_service):
    types = await graph_service.list_edge_types()
    names = {t.name for t in types}
    assert "RELATES_TO" in names
    assert "MENTIONS" in names


@pytest.mark.asyncio
async def test_create_and_get_node_type(graph_service):
    nt = await graph_service.create_node_type("Test_CustomType", "A test type")
    assert nt.name == "Test_CustomType"
    fetched = await graph_service.get_node_type(nt.id)
    assert fetched is not None
    assert fetched.name == "Test_CustomType"


@pytest.mark.asyncio
async def test_update_node_type(graph_service):
    nt = await graph_service.create_node_type("Test_Updateable", "Before")
    updated = await graph_service.update_node_type(nt.id, description="After")
    assert updated.description == "After"
    assert updated.name == "Test_Updateable"


@pytest.mark.asyncio
async def test_delete_node_type(graph_service):
    nt = await graph_service.create_node_type("Test_Deleteable", "To be deleted")
    assert await graph_service.delete_node_type(nt.id)
    assert await graph_service.get_node_type(nt.id) is None
