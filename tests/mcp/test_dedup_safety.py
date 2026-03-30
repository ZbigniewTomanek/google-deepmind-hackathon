"""Tests for adapter-level dedup safety nets (Plan 16, Stage 4).

Tests cover:
- Name-primary node dedup with merge-safe type heuristic
- Source-target primary edge dedup
- _types_are_merge_safe unit tests
- Drift/homonym logging
"""

import pytest

from neocortex.db.adapter import _HOMONYM_TYPE_GROUPS, _MERGE_SAFE_TYPE_GROUPS, _TYPE_TO_GROUP, _types_are_merge_safe

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


# ── Semantic type hierarchy tests ──


class TestMergeSafeTypeGroups:
    """Tests for the configurable merge-safe type group system (Plan 17, Stage 3)."""

    def test_type_to_group_lookup_populated(self):
        """Pre-computed lookup has entries for all types in all groups."""
        total_types = sum(len(g) for g in _MERGE_SAFE_TYPE_GROUPS)
        assert len(_TYPE_TO_GROUP) == total_types

    def test_type_to_group_is_case_insensitive(self):
        """Lookup keys are lowercase."""
        for key in _TYPE_TO_GROUP:
            assert key == key.lower()

    # Software group — sibling types that should merge
    def test_tool_project_merged(self):
        assert _types_are_merge_safe("Tool", "Project") is True

    def test_tool_software_merged(self):
        assert _types_are_merge_safe("Tool", "Software") is True

    def test_framework_library_merged(self):
        assert _types_are_merge_safe("Framework", "Library") is True

    def test_software_tool_in_group(self):
        assert _types_are_merge_safe("SoftwareTool", "Library") is True

    # People group
    def test_person_teammember_merged(self):
        assert _types_are_merge_safe("Person", "TeamMember") is True

    def test_person_employee_merged(self):
        assert _types_are_merge_safe("Person", "Employee") is True

    def test_researcher_scientist_merged(self):
        assert _types_are_merge_safe("Researcher", "Scientist") is True

    # Organization group
    def test_team_organization_merged(self):
        assert _types_are_merge_safe("Team", "Organization") is True

    def test_company_department_merged(self):
        assert _types_are_merge_safe("Company", "Department") is True

    # Concept group
    def test_concept_topic_merged(self):
        assert _types_are_merge_safe("Concept", "Topic") is True

    # Technology group
    def test_technology_protocol_merged(self):
        assert _types_are_merge_safe("Technology", "Protocol") is True

    # Document group
    def test_document_article_merged(self):
        assert _types_are_merge_safe("Document", "Article") is True

    # Event group
    def test_event_milestone_merged(self):
        assert _types_are_merge_safe("Event", "Milestone") is True

    # Metric group
    def test_metric_measurement_merged(self):
        assert _types_are_merge_safe("Metric", "Measurement") is True

    # Homonym blacklist overrides group membership
    def test_homonym_overrides_person_organization(self):
        """Person and Organization are both in groups, but the homonym blacklist wins."""
        assert _types_are_merge_safe("Person", "Organization") is False

    def test_homonym_overrides_metric_metricunit(self):
        """Metric/MetricUnit: homonym blacklist prevents prefix merge."""
        assert _types_are_merge_safe("Metric", "MetricUnit") is False

    # Types excluded from groups — too distinct to auto-merge
    def test_service_application_not_merged(self):
        assert _types_are_merge_safe("Service", "Application") is False

    def test_meeting_sprint_not_merged(self):
        assert _types_are_merge_safe("Meeting", "Sprint") is False

    def test_platform_library_not_merged(self):
        assert _types_are_merge_safe("Platform", "Library") is False

    # Cross-group types should not merge
    def test_person_tool_not_merged(self):
        assert _types_are_merge_safe("Person", "Tool") is False

    def test_organization_document_not_merged(self):
        assert _types_are_merge_safe("Organization", "Document") is False

    # Unknown types default to conservative
    def test_unknown_types_not_merged(self):
        assert _types_are_merge_safe("Aardvark", "Zebra") is False

    # Case insensitivity for group lookup
    def test_group_lookup_case_insensitive(self):
        assert _types_are_merge_safe("tool", "project") is True
        assert _types_are_merge_safe("TOOL", "PROJECT") is True
        assert _types_are_merge_safe("Tool", "project") is True


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


@pytest.mark.asyncio
async def test_node_dedup_tool_project_merges(mock_repo):
    """Same name, Tool/Project types (same merge group) → merges. Validates DataForge fix."""
    nt_tool = await mock_repo.get_or_create_node_type("agent", "Tool")
    nt_project = await mock_repo.get_or_create_node_type("agent", "Project")

    node1 = await mock_repo.upsert_node("agent", "DataForge", nt_tool.id, content="Data processing tool")
    node2 = await mock_repo.upsert_node("agent", "DataForge", nt_project.id, content="Data processing project")

    assert node1.id == node2.id
    assert node2.content == "Data processing project"
    all_names = await mock_repo.list_all_node_names("agent")
    assert all_names.count("DataForge") == 1


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


# ── Drift/homonym log emission tests ──


@pytest.mark.asyncio
async def test_node_type_drift_emits_log(mock_repo):
    """Verify node_type_drift_caught is logged when merge-safe types drift."""
    from loguru import logger

    nt_person = await mock_repo.get_or_create_node_type("agent", "Person")
    nt_employee = await mock_repo.get_or_create_node_type("agent", "PersonEmployee")

    await mock_repo.upsert_node("agent", "Alice", nt_person.id, content="Engineer")

    messages = []
    handler_id = logger.add(lambda msg: messages.append(msg.record["message"]), level="INFO")
    try:
        await mock_repo.upsert_node("agent", "Alice", nt_employee.id, content="Senior Engineer")
    finally:
        logger.remove(handler_id)

    assert any("node_type_drift_caught" in m for m in messages), f"Expected drift log, got: {messages}"


@pytest.mark.asyncio
async def test_node_homonym_emits_log(mock_repo):
    """Verify node_homonym_detected is logged for incompatible types."""
    from loguru import logger

    nt_drug = await mock_repo.get_or_create_node_type("agent", "Drug")
    nt_neuro = await mock_repo.get_or_create_node_type("agent", "Neurotransmitter")

    await mock_repo.upsert_node("agent", "Serotonin", nt_drug.id, content="SSRI target")

    messages = []
    handler_id = logger.add(lambda msg: messages.append(msg.record["message"]), level="INFO")
    try:
        await mock_repo.upsert_node("agent", "Serotonin", nt_neuro.id, content="5-HT")
    finally:
        logger.remove(handler_id)

    assert any("node_homonym_detected" in m for m in messages), f"Expected homonym log, got: {messages}"


@pytest.mark.asyncio
async def test_edge_type_drift_emits_log(mock_repo):
    """Verify edge_type_drift_caught is logged on single-edge type update."""
    from loguru import logger

    nt = await mock_repo.get_or_create_node_type("agent", "Person")
    et1 = await mock_repo.get_or_create_edge_type("agent", "WORKS_WITH")
    et2 = await mock_repo.get_or_create_edge_type("agent", "COLLABORATES_WITH")

    alice = await mock_repo.upsert_node("agent", "Alice", nt.id)
    bob = await mock_repo.upsert_node("agent", "Bob", nt.id)

    await mock_repo.upsert_edge("agent", alice.id, bob.id, et1.id)

    messages = []
    handler_id = logger.add(lambda msg: messages.append(msg.record["message"]), level="INFO")
    try:
        await mock_repo.upsert_edge("agent", alice.id, bob.id, et2.id)
    finally:
        logger.remove(handler_id)

    assert any("edge_type_drift_caught" in m for m in messages), f"Expected edge drift log, got: {messages}"


# ── Prefix heuristic tests (no arbitrary substring false positives) ──


class TestTypesAreMergeSafePrefixOnly:
    """Verify that the merge heuristic uses prefix matching, not arbitrary substring."""

    def test_api_capital_not_merged(self):
        assert _types_are_merge_safe("API", "Capital") is False

    def test_event_prevent_not_merged(self):
        assert _types_are_merge_safe("Event", "Prevent") is False

    def test_fact_artifact_not_merged(self):
        assert _types_are_merge_safe("Fact", "Artifact") is False

    def test_log_catalog_not_merged(self):
        assert _types_are_merge_safe("Log", "Catalog") is False

    def test_ai_mountain_not_merged(self):
        assert _types_are_merge_safe("AI", "Mountain") is False

    def test_event_eventtype_merged(self):
        """Prefix match at type hierarchy boundary should still merge."""
        assert _types_are_merge_safe("Event", "EventType") is True


# ── Edge type normalization tests (Plan 17, Stage 4) ──


@pytest.mark.asyncio
async def test_edge_type_normalization_pascal_to_screaming(mock_repo):
    """PascalCase → SCREAMING_SNAKE before storage."""
    et1 = await mock_repo.get_or_create_edge_type("agent", "RelatesTo")
    et2 = await mock_repo.get_or_create_edge_type("agent", "RELATES_TO")
    assert et1.id == et2.id  # same type
    assert et1.name == "RELATES_TO"


@pytest.mark.asyncio
async def test_edge_type_normalization_camel_case(mock_repo):
    """camelCase → SCREAMING_SNAKE before storage."""
    et1 = await mock_repo.get_or_create_edge_type("agent", "hasMember")
    et2 = await mock_repo.get_or_create_edge_type("agent", "HAS_MEMBER")
    assert et1.id == et2.id
    assert et1.name == "HAS_MEMBER"


@pytest.mark.asyncio
async def test_edge_type_normalization_lower_with_spaces(mock_repo):
    """lower case with spaces → SCREAMING_SNAKE before storage."""
    et1 = await mock_repo.get_or_create_edge_type("agent", "works on")
    et2 = await mock_repo.get_or_create_edge_type("agent", "WORKS_ON")
    assert et1.id == et2.id
    assert et1.name == "WORKS_ON"


@pytest.mark.asyncio
async def test_edge_type_idempotent(mock_repo):
    """Normalization is idempotent — already SCREAMING_SNAKE stays the same."""
    et = await mock_repo.get_or_create_edge_type("agent", "MEMBER_OF")
    assert et.name == "MEMBER_OF"


@pytest.mark.asyncio
async def test_node_type_normalization_snake_to_pascal(mock_repo):
    """snake_case → PascalCase before storage."""
    nt1 = await mock_repo.get_or_create_node_type("agent", "software_tool")
    nt2 = await mock_repo.get_or_create_node_type("agent", "SoftwareTool")
    assert nt1.id == nt2.id
    assert nt1.name == "SoftwareTool"


@pytest.mark.asyncio
async def test_node_type_normalization_idempotent(mock_repo):
    """Already PascalCase stays the same."""
    nt = await mock_repo.get_or_create_node_type("agent", "Person")
    assert nt.name == "Person"


@pytest.mark.asyncio
async def test_node_type_normalization_with_spaces(mock_repo):
    """Space-separated → PascalCase before storage."""
    nt1 = await mock_repo.get_or_create_node_type("agent", "software tool")
    nt2 = await mock_repo.get_or_create_node_type("agent", "SoftwareTool")
    assert nt1.id == nt2.id
    assert nt1.name == "SoftwareTool"


@pytest.mark.asyncio
async def test_edge_type_normalization_kebab_case(mock_repo):
    """kebab-case → SCREAMING_SNAKE before storage."""
    et1 = await mock_repo.get_or_create_edge_type("agent", "works-with")
    et2 = await mock_repo.get_or_create_edge_type("agent", "WORKS_WITH")
    assert et1.id == et2.id
    assert et1.name == "WORKS_WITH"


@pytest.mark.asyncio
async def test_edge_type_normalization_mixed_format(mock_repo):
    """Mixed Has_Member → HAS_MEMBER before storage."""
    et1 = await mock_repo.get_or_create_edge_type("agent", "Has_Member")
    et2 = await mock_repo.get_or_create_edge_type("agent", "HAS_MEMBER")
    assert et1.id == et2.id
    assert et1.name == "HAS_MEMBER"
