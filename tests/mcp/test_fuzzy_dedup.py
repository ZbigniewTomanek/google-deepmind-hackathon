"""Tests for fuzzy name matching and alias-based dedup (Plan 17, Stage 2).

Tests cover:
- Alias resolution via register_alias / resolve_alias
- Fuzzy matching via find_nodes_fuzzy (names_are_similar in mock)
- Phase 1.5 integration in upsert_node (alias → trigram fallback)
- Auto-alias registration on insert with parenthetical names
- Exact match still preferred over fuzzy (no regression)
- Fuzzy match + type compatibility (Phase 1.5 → Phase 3 chain)
- No false positive merging across unrelated names
"""

import pytest

from neocortex.db.mock import InMemoryRepository


@pytest.fixture
def repo() -> InMemoryRepository:
    return InMemoryRepository()


# ── Alias Resolution ──


@pytest.mark.asyncio
async def test_register_and_resolve_alias(repo: InMemoryRepository):
    """Register an alias for a node and resolve it back."""
    nt = await repo.get_or_create_node_type("agent", "Drug")
    node = await repo.upsert_node("agent", "Fluoxetine", nt.id, content="SSRI")

    await repo.register_alias("agent", node.id, "Prozac")
    resolved = await repo.resolve_alias("agent", "Prozac")

    assert len(resolved) == 1
    assert resolved[0].id == node.id
    assert resolved[0].name == "Fluoxetine"


@pytest.mark.asyncio
async def test_resolve_alias_case_insensitive(repo: InMemoryRepository):
    """Alias resolution is case-insensitive."""
    nt = await repo.get_or_create_node_type("agent", "Drug")
    node = await repo.upsert_node("agent", "Fluoxetine", nt.id)

    await repo.register_alias("agent", node.id, "Prozac")
    resolved = await repo.resolve_alias("agent", "prozac")

    assert len(resolved) == 1
    assert resolved[0].id == node.id


@pytest.mark.asyncio
async def test_resolve_alias_nonexistent_returns_empty(repo: InMemoryRepository):
    """Resolving a non-existent alias returns empty list."""
    resolved = await repo.resolve_alias("agent", "NoSuchAlias")
    assert resolved == []


@pytest.mark.asyncio
async def test_register_alias_idempotent(repo: InMemoryRepository):
    """Registering the same alias twice for the same node is a no-op."""
    nt = await repo.get_or_create_node_type("agent", "Drug")
    node = await repo.upsert_node("agent", "Fluoxetine", nt.id)

    await repo.register_alias("agent", node.id, "Prozac")
    await repo.register_alias("agent", node.id, "Prozac")

    resolved = await repo.resolve_alias("agent", "Prozac")
    assert len(resolved) == 1


@pytest.mark.asyncio
async def test_alias_can_point_to_multiple_nodes(repo: InMemoryRepository):
    """Same alias can point to multiple nodes (ambiguous alias)."""
    nt_drug = await repo.get_or_create_node_type("agent", "Drug")
    nt_concept = await repo.get_or_create_node_type("agent", "Concept")

    node1 = await repo.upsert_node("agent", "Aspirin", nt_drug.id, content="Pain reliever")
    node2 = await repo.upsert_node("agent", "Aspirin Concept", nt_concept.id, content="General concept")

    await repo.register_alias("agent", node1.id, "ASA")
    await repo.register_alias("agent", node2.id, "ASA")

    resolved = await repo.resolve_alias("agent", "ASA")
    assert len(resolved) == 2


# ── find_nodes_fuzzy ──


@pytest.mark.asyncio
async def test_find_nodes_fuzzy_by_name_similarity(repo: InMemoryRepository):
    """Fuzzy search finds nodes by name similarity (multi-word containment)."""
    nt = await repo.get_or_create_node_type("agent", "Person")
    await repo.upsert_node("agent", "John Robert Doe", nt.id, content="Full name")

    # Multi-word containment: "John Doe" words ⊆ "John Robert Doe" words
    results = await repo.find_nodes_fuzzy("agent", "John Doe")
    assert len(results) >= 1
    assert results[0][0].name == "John Robert Doe"


@pytest.mark.asyncio
async def test_find_nodes_fuzzy_by_alias(repo: InMemoryRepository):
    """Fuzzy search finds nodes via alias table."""
    nt = await repo.get_or_create_node_type("agent", "Drug")
    node = await repo.upsert_node("agent", "Fluoxetine", nt.id)
    await repo.register_alias("agent", node.id, "Prozac")

    results = await repo.find_nodes_fuzzy("agent", "Prozac")
    assert len(results) >= 1
    assert results[0][0].name == "Fluoxetine"


@pytest.mark.asyncio
async def test_find_nodes_fuzzy_no_false_positive(repo: InMemoryRepository):
    """Unrelated names should NOT match in fuzzy search."""
    nt = await repo.get_or_create_node_type("agent", "Person")
    await repo.upsert_node("agent", "Alice", nt.id)

    results = await repo.find_nodes_fuzzy("agent", "Bob")
    assert len(results) == 0


@pytest.mark.asyncio
async def test_find_nodes_fuzzy_excludes_forgotten(repo: InMemoryRepository):
    """Forgotten nodes should not appear in fuzzy search results."""
    nt = await repo.get_or_create_node_type("agent", "Tool")
    node = await repo.upsert_node("agent", "Apache Kafka", nt.id)
    await repo.mark_forgotten("agent", [node.id])

    results = await repo.find_nodes_fuzzy("agent", "Kafka")
    assert len(results) == 0


# ── Phase 1.5 in upsert_node ──


@pytest.mark.asyncio
async def test_upsert_alias_resolution_merges(repo: InMemoryRepository):
    """upsert_node Phase 1.5a: alias lookup merges into existing node."""
    nt = await repo.get_or_create_node_type("agent", "Drug")
    node1 = await repo.upsert_node("agent", "Fluoxetine", nt.id, content="SSRI")
    await repo.register_alias("agent", node1.id, "Prozac")

    # Upsert with the alias name — should merge into Fluoxetine node
    node2 = await repo.upsert_node("agent", "Prozac", nt.id, content="Brand name SSRI")

    assert node1.id == node2.id
    assert node2.content == "Brand name SSRI"


@pytest.mark.asyncio
async def test_upsert_fuzzy_match_via_alias(repo: InMemoryRepository):
    """upsert_node Phase 1.5a: alias lookup merges 'Kafka' into 'Apache Kafka'.

    Note: single-word fuzzy matching is intentionally conservative in the mock
    (names_are_similar requires 2+ word overlap). In production, the PG adapter
    uses trigram similarity for single-word matches like 'Kafka' → 'Apache Kafka'.
    This test uses the alias path which works identically in both mock and PG.
    """
    nt = await repo.get_or_create_node_type("agent", "Tool")
    node1 = await repo.upsert_node("agent", "Apache Kafka", nt.id, content="Event streaming")
    await repo.register_alias("agent", node1.id, "Kafka")

    # "Kafka" should resolve via alias to "Apache Kafka"
    node2 = await repo.upsert_node("agent", "Kafka", nt.id, content="Message broker")

    assert node1.id == node2.id
    assert node2.content == "Message broker"


@pytest.mark.asyncio
async def test_upsert_exact_match_preferred_over_fuzzy(repo: InMemoryRepository):
    """Exact name match (Phase 1) takes priority over fuzzy (Phase 1.5)."""
    nt = await repo.get_or_create_node_type("agent", "Tool")
    node1 = await repo.upsert_node("agent", "Kafka", nt.id, content="Short name")

    # Exact match should be used, not fuzzy
    node2 = await repo.upsert_node("agent", "Kafka", nt.id, content="Updated")

    assert node1.id == node2.id
    assert node2.content == "Updated"
    # Should still be only 1 node
    all_names = await repo.list_all_node_names("agent")
    assert len(all_names) == 1


@pytest.mark.asyncio
async def test_upsert_phase15_only_triggers_when_phase1_empty(repo: InMemoryRepository):
    """Phase 1.5 only fires when Phase 1 returns zero rows."""
    nt_tool = await repo.get_or_create_node_type("agent", "Tool")
    nt_concept = await repo.get_or_create_node_type("agent", "Concept")

    # Create "Kafka" as a Tool
    node1 = await repo.upsert_node("agent", "Kafka", nt_tool.id, content="Tool node")
    # Also create "Apache Kafka" as a Tool
    await repo.upsert_node("agent", "Apache Kafka", nt_tool.id, content="Full name")

    # Now upsert "Kafka" again — should use Phase 1 exact match, NOT fuzzy to "Apache Kafka"
    node3 = await repo.upsert_node("agent", "Kafka", nt_concept.id, content="Concept of Kafka")

    # Phase 1 found "Kafka" by exact name, Phase 3 checked type compatibility
    # Since Tool and Concept are not merge-safe, it should create a separate node
    assert node3.id != node1.id


@pytest.mark.asyncio
async def test_auto_alias_registration_on_parenthetical_insert(repo: InMemoryRepository):
    """Auto-alias registration: 'Fluoxetine (Prozac)' registers 'Prozac' as alias."""
    nt = await repo.get_or_create_node_type("agent", "Drug")
    node = await repo.upsert_node("agent", "Fluoxetine (Prozac)", nt.id, content="SSRI")

    # The canonical name should be "Fluoxetine", with "Prozac" as alias
    assert node.name == "Fluoxetine"

    # The alias should be registered
    resolved = await repo.resolve_alias("agent", "Prozac")
    assert len(resolved) == 1
    assert resolved[0].id == node.id


@pytest.mark.asyncio
async def test_fuzzy_match_with_type_compatibility_chain(repo: InMemoryRepository):
    """Phase 1.5 alias match feeds into Phase 2/3 type compatibility check."""
    nt_tool = await repo.get_or_create_node_type("agent", "Tool")
    nt_person = await repo.get_or_create_node_type("agent", "Person")

    # Create "Apache Kafka" as a Tool, register alias
    node1 = await repo.upsert_node("agent", "Apache Kafka", nt_tool.id, content="Event streaming")
    await repo.register_alias("agent", node1.id, "Kafka")

    # Alias resolves "Kafka" → "Apache Kafka", but type is incompatible (Person)
    # Phase 3 should reject the merge
    node2 = await repo.upsert_node("agent", "Kafka", nt_person.id, content="Franz Kafka")

    assert node1.id != node2.id
    all_names = await repo.list_all_node_names("agent")
    assert len(all_names) == 2


@pytest.mark.asyncio
async def test_upsert_no_false_positive_fuzzy_merge(repo: InMemoryRepository):
    """Unrelated names should NOT be fuzzy-merged."""
    nt = await repo.get_or_create_node_type("agent", "Person")
    node1 = await repo.upsert_node("agent", "Alice", nt.id, content="Person A")
    node2 = await repo.upsert_node("agent", "Bob", nt.id, content="Person B")

    assert node1.id != node2.id
    all_names = await repo.list_all_node_names("agent")
    assert len(all_names) == 2


@pytest.mark.asyncio
async def test_alias_match_with_merge_safe_types(repo: InMemoryRepository):
    """Phase 1.5 alias match + Phase 3 merge-safe types → merge."""
    nt_sw = await repo.get_or_create_node_type("agent", "Software")
    nt_tool = await repo.get_or_create_node_type("agent", "SoftwareTool")

    # Create "Apache Kafka" as Software, register alias
    node1 = await repo.upsert_node("agent", "Apache Kafka", nt_sw.id, content="Event streaming")
    await repo.register_alias("agent", node1.id, "Kafka")

    # Alias resolves "Kafka" → "Apache Kafka" with compatible type → should merge
    node2 = await repo.upsert_node("agent", "Kafka", nt_tool.id, content="Message broker")

    assert node1.id == node2.id
    assert node2.content == "Message broker"
