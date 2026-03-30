"""Tests for adapter-level dedup safety nets (Plan 16, Stage 4).

Tests cover:
- Name-primary node dedup with merge-safe type heuristic
- Source-target primary edge dedup
- _types_are_merge_safe unit tests
- Drift/homonym logging
"""

import pytest

from neocortex.db.adapter import _HOMONYM_TYPE_GROUPS, _types_are_merge_safe

# ── _types_are_merge_safe unit tests ──


class TestTypesAreMergeSafe:
    def test_same_type_returns_true(self):
        assert _types_are_merge_safe("Person", "Person") is True

    def test_none_existing_returns_false(self):
        assert _types_are_merge_safe(None, "Person") is False

    def test_none_requested_returns_false(self):
        assert _types_are_merge_safe("Person", None) is False

    def test_both_none_returns_false(self):
        assert _types_are_merge_safe(None, None) is False

    def test_empty_string_returns_false(self):
        assert _types_are_merge_safe("", "Person") is False

    def test_substring_related_returns_true(self):
        assert _types_are_merge_safe("Software", "SoftwareTool") is True
        assert _types_are_merge_safe("SoftwareTool", "Software") is True

    def test_person_person_role_returns_true(self):
        assert _types_are_merge_safe("Person", "PersonRole") is True

    def test_known_homonym_drug_neurotransmitter_returns_false(self):
        assert _types_are_merge_safe("Drug", "Neurotransmitter") is False
        assert _types_are_merge_safe("Neurotransmitter", "Drug") is False

    def test_known_homonym_person_organization_returns_false(self):
        assert _types_are_merge_safe("Person", "Organization") is False

    def test_known_homonym_language_country_returns_false(self):
        assert _types_are_merge_safe("Language", "Country") is False

    def test_unrelated_types_returns_false(self):
        assert _types_are_merge_safe("Person", "Software") is False
        assert _types_are_merge_safe("City", "Company") is False

    def test_case_insensitive_substring(self):
        assert _types_are_merge_safe("person", "PersonRole") is True
        assert _types_are_merge_safe("PERSON", "personrole") is True

    def test_homonym_groups_are_frozen(self):
        assert isinstance(_HOMONYM_TYPE_GROUPS, frozenset)
        for group in _HOMONYM_TYPE_GROUPS:
            assert isinstance(group, frozenset)


# ── Node dedup safety tests (InMemoryRepository) ──


@pytest.mark.asyncio
async def test_node_dedup_same_name_compatible_types_merges(mock_repo):
    """Same name, compatible types (Person/Employee substring) → merges, no duplicate."""
    nt_person = await mock_repo.get_or_create_node_type("agent", "Person")
    nt_employee = await mock_repo.get_or_create_node_type("agent", "PersonEmployee")

    node1 = await mock_repo.upsert_node("agent", "Alice", nt_person.id, content="Engineer at Acme")
    node2 = await mock_repo.upsert_node("agent", "Alice", nt_employee.id, content="Senior Engineer")

    # Should merge into the same node (same id)
    assert node1.id == node2.id
    assert node2.content == "Senior Engineer"
    # Only 1 node in total
    all_names = await mock_repo.list_all_node_names("agent")
    assert len(all_names) == 1


@pytest.mark.asyncio
async def test_node_dedup_same_name_incompatible_types_creates_separate(mock_repo):
    """Same name, incompatible types (Drug/Neurotransmitter) → creates separate node."""
    nt_drug = await mock_repo.get_or_create_node_type("agent", "Drug")
    nt_neuro = await mock_repo.get_or_create_node_type("agent", "Neurotransmitter")

    node1 = await mock_repo.upsert_node("agent", "Serotonin", nt_drug.id, content="SSRI target")
    node2 = await mock_repo.upsert_node("agent", "Serotonin", nt_neuro.id, content="5-HT neurotransmitter")

    # Should be separate nodes
    assert node1.id != node2.id
    all_names = await mock_repo.list_all_node_names("agent")
    assert len(all_names) == 2


@pytest.mark.asyncio
async def test_node_dedup_substring_types_merges(mock_repo):
    """Same name, substring-related types (Software/SoftwareTool) → merges."""
    nt_sw = await mock_repo.get_or_create_node_type("agent", "Software")
    nt_tool = await mock_repo.get_or_create_node_type("agent", "SoftwareTool")

    node1 = await mock_repo.upsert_node("agent", "VSCode", nt_sw.id, content="Code editor")
    node2 = await mock_repo.upsert_node("agent", "VSCode", nt_tool.id, content="IDE by Microsoft")

    assert node1.id == node2.id
    assert node2.content == "IDE by Microsoft"


@pytest.mark.asyncio
async def test_node_dedup_exact_type_match_preferred(mock_repo):
    """Same name, exact (name, type_id) match → always preferred over name-only."""
    nt_person = await mock_repo.get_or_create_node_type("agent", "Person")
    node1 = await mock_repo.upsert_node("agent", "Alice", nt_person.id, content="V1")
    node2 = await mock_repo.upsert_node("agent", "Alice", nt_person.id, content="V2")

    assert node1.id == node2.id
    assert node2.content == "V2"


@pytest.mark.asyncio
async def test_node_dedup_multi_homonym_matches_by_type(mock_repo):
    """Same name, 2+ existing nodes → matches by type (no merge across types)."""
    nt_lang = await mock_repo.get_or_create_node_type("agent", "Language")
    nt_country = await mock_repo.get_or_create_node_type("agent", "Country")
    nt_food = await mock_repo.get_or_create_node_type("agent", "Food")

    # Create two separate nodes (known homonym)
    node1 = await mock_repo.upsert_node("agent", "Turkish", nt_lang.id, content="Language spoken in Turkey")
    node2 = await mock_repo.upsert_node("agent", "Turkish", nt_country.id, content="Relating to Turkey")

    assert node1.id != node2.id

    # Now a third upsert with a completely new type: since 2+ exist, no merging
    node3 = await mock_repo.upsert_node("agent", "Turkish", nt_food.id, content="A type of coffee")

    assert node3.id != node1.id
    assert node3.id != node2.id
    all_names = await mock_repo.list_all_node_names("agent")
    assert all_names.count("Turkish") == 3


@pytest.mark.asyncio
async def test_node_dedup_properties_merged(mock_repo):
    """Content and properties correctly merged in merge cases."""
    nt_person = await mock_repo.get_or_create_node_type("agent", "Person")
    nt_employee = await mock_repo.get_or_create_node_type("agent", "PersonEmployee")

    node1 = await mock_repo.upsert_node("agent", "Bob", nt_person.id, content="Bob", properties={"role": "engineer"})
    node2 = await mock_repo.upsert_node(
        "agent", "Bob", nt_employee.id, content="Bob Smith", properties={"team": "infra"}
    )

    assert node1.id == node2.id
    assert node2.content == "Bob Smith"
    assert node2.properties["role"] == "engineer"  # preserved from first
    assert node2.properties["team"] == "infra"  # added from second


# ── Edge dedup safety tests (InMemoryRepository) ──


@pytest.mark.asyncio
async def test_edge_dedup_same_st_different_type_single_existing_updates(mock_repo):
    """Same source-target, different edge type, 1 existing → updates existing edge."""
    nt = await mock_repo.get_or_create_node_type("agent", "Person")
    et1 = await mock_repo.get_or_create_edge_type("agent", "WORKS_WITH")
    et2 = await mock_repo.get_or_create_edge_type("agent", "COLLABORATES_WITH")

    alice = await mock_repo.upsert_node("agent", "Alice", nt.id)
    bob = await mock_repo.upsert_node("agent", "Bob", nt.id)

    edge1 = await mock_repo.upsert_edge("agent", alice.id, bob.id, et1.id)
    edge2 = await mock_repo.upsert_edge("agent", alice.id, bob.id, et2.id)

    # Should update the same edge
    assert edge1.id == edge2.id
    assert edge2.type_id == et2.id  # type updated to new
    # Only 1 edge total
    sigs = await mock_repo.list_all_edge_signatures("agent")
    assert len(sigs) == 1


@pytest.mark.asyncio
async def test_edge_dedup_same_st_different_type_multiple_existing_adds(mock_repo):
    """Same source-target, different edge type, 2+ existing → adds normally."""
    nt = await mock_repo.get_or_create_node_type("agent", "Person")
    et1 = await mock_repo.get_or_create_edge_type("agent", "KNOWS")
    et2 = await mock_repo.get_or_create_edge_type("agent", "WORKS_WITH")
    et3 = await mock_repo.get_or_create_edge_type("agent", "MANAGES")

    alice = await mock_repo.upsert_node("agent", "Alice", nt.id)
    bob = await mock_repo.upsert_node("agent", "Bob", nt.id)

    # Create two edges between alice and bob (bypassing dedup by creating first via exact match)
    await mock_repo.upsert_edge("agent", alice.id, bob.id, et1.id)
    await mock_repo.upsert_edge("agent", alice.id, bob.id, et1.id)  # exact match, update
    # Now add second distinct type
    await mock_repo.upsert_edge("agent", alice.id, bob.id, et2.id)

    # At this point 1 edge of et1 and 1 of et2 exist (dedup merged et1's second call)
    # But the dedup converted the first et2 from et1 to et2 since there was only 1 edge
    # So let's explicitly set up the 2+ case by using direct insertion
    # Reset and create 2 edges explicitly
    mock_repo._edges.clear()
    mock_repo._next_edge_id = 1
    edge1 = await mock_repo.upsert_edge("agent", alice.id, bob.id, et1.id)
    # Force a second edge with et2 by bypassing dedup
    from datetime import UTC, datetime

    from neocortex.models import Edge

    forced_edge = Edge(
        id=mock_repo._next_edge_id,
        source_id=alice.id,
        target_id=bob.id,
        type_id=et2.id,
        weight=1.0,
        properties={},
        created_at=datetime.now(UTC),
    )
    mock_repo._next_edge_id += 1
    mock_repo._edges[forced_edge.id] = forced_edge

    # Now 2 edges exist between alice and bob. Adding a 3rd type should add normally
    edge3 = await mock_repo.upsert_edge("agent", alice.id, bob.id, et3.id)

    assert edge3.id != edge1.id
    assert edge3.id != forced_edge.id
    sigs = await mock_repo.list_all_edge_signatures("agent")
    assert len(sigs) == 3


@pytest.mark.asyncio
async def test_edge_dedup_properties_merged(mock_repo):
    """Properties correctly merged when edge type drift is caught."""
    nt = await mock_repo.get_or_create_node_type("agent", "Person")
    et1 = await mock_repo.get_or_create_edge_type("agent", "WORKS_AT")
    et2 = await mock_repo.get_or_create_edge_type("agent", "EMPLOYED_BY")

    alice = await mock_repo.upsert_node("agent", "Alice", nt.id)
    bob = await mock_repo.upsert_node("agent", "Bob", nt.id)

    await mock_repo.upsert_edge("agent", alice.id, bob.id, et1.id, properties={"since": "2020"})
    edge2 = await mock_repo.upsert_edge("agent", alice.id, bob.id, et2.id, properties={"role": "lead"})

    assert edge2.properties["since"] == "2020"
    assert edge2.properties["role"] == "lead"


@pytest.mark.asyncio
async def test_edge_dedup_exact_type_match_preferred(mock_repo):
    """Same source-target-type → normal upsert (no drift logic)."""
    nt = await mock_repo.get_or_create_node_type("agent", "Person")
    et = await mock_repo.get_or_create_edge_type("agent", "KNOWS")

    alice = await mock_repo.upsert_node("agent", "Alice", nt.id)
    bob = await mock_repo.upsert_node("agent", "Bob", nt.id)

    edge1 = await mock_repo.upsert_edge("agent", alice.id, bob.id, et.id, weight=0.5)
    edge2 = await mock_repo.upsert_edge("agent", alice.id, bob.id, et.id, weight=0.8)

    assert edge1.id == edge2.id
    assert edge2.weight == 0.8
