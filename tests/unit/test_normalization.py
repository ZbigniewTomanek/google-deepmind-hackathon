"""Unit tests for entity name and type normalization utilities."""

from __future__ import annotations

import pytest

from neocortex.normalization import (
    canonicalize_name,
    names_are_similar,
    normalize_edge_type,
    normalize_node_type,
)

# --- canonicalize_name ---


@pytest.mark.parametrize(
    "input_name, expected",
    [
        # Parenthetical alias extraction
        ("Fluoxetine (Prozac)", ("Fluoxetine", ["Prozac"])),
        (
            "serotonin (5-hydroxytryptamine, 5-HT)",
            ("Serotonin", ["5-hydroxytryptamine, 5-HT"]),
        ),
        # No parenthetical
        ("Apache Kafka", ("Apache Kafka", [])),
        # Whitespace collapsing + all-lowercase title casing
        ("  apache   kafka  ", ("Apache Kafka", [])),
        # Mixed case preservation
        ("gRPC", ("gRPC", [])),
        ("iOS", ("iOS", [])),
        ("PostgreSQL", ("PostgreSQL", [])),
        ("DataForge", ("DataForge", [])),
        # Acronym preservation in title-cased output
        ("5-HT", ("5-HT", [])),
        # All-lowercase with known acronyms
        ("rest api", ("REST API", [])),
        ("sql database", ("SQL Database", [])),
        # Empty / whitespace-only
        ("", ("", [])),
        ("   ", ("", [])),
        # Single word, already correct
        ("Python", ("Python", [])),
        # Single word, all lowercase
        ("python", ("Python", [])),
    ],
)
def test_canonicalize_name(input_name: str, expected: tuple[str, list[str]]) -> None:
    assert canonicalize_name(input_name) == expected


# --- normalize_edge_type ---


@pytest.mark.parametrize(
    "input_type, expected",
    [
        ("RelatesTo", "RELATES_TO"),
        ("relates_to", "RELATES_TO"),
        ("RELATES_TO", "RELATES_TO"),  # idempotent
        ("relates-to", "RELATES_TO"),
        ("hasMember", "HAS_MEMBER"),
        ("MEMBER_OF", "MEMBER_OF"),  # idempotent
        ("RELATES TO", "RELATES_TO"),  # space → underscore
        ("relates  to", "RELATES_TO"),  # multiple spaces
        ("usedBy", "USED_BY"),
    ],
)
def test_normalize_edge_type(input_type: str, expected: str) -> None:
    result = normalize_edge_type(input_type)
    assert result == expected
    # Verify idempotent
    assert normalize_edge_type(result) == result


# --- normalize_node_type ---


@pytest.mark.parametrize(
    "input_type, expected",
    [
        ("SoftwareTool", "SoftwareTool"),  # idempotent
        ("software_tool", "SoftwareTool"),  # snake_case → PascalCase
        ("SOFTWARE_TOOL", "SoftwareTool"),  # ALL_CAPS with separator → PascalCase
        ("SOFTWARETOOL", "SOFTWARETOOL"),  # ALL_CAPS no separator → preserve
        ("Person", "Person"),  # idempotent
        ("gRPC", "GRPC"),  # mixed case → uppercase start enforced
        ("software tool", "SoftwareTool"),  # space-separated → PascalCase
    ],
)
def test_normalize_node_type(input_type: str, expected: str) -> None:
    result = normalize_node_type(input_type)
    assert result == expected


# --- normalize_node_type: invalid character rejection ---


def test_node_type_strips_json_corruption():
    """Invalid chars like } are stripped; valid remainder passes through."""
    assert normalize_node_type("Constraint}OceanScience") == "ConstraintOceanScience"


def test_node_type_strips_and_rejects_only_invalid():
    """If only invalid chars remain after stripping, raise ValueError."""
    with pytest.raises(ValueError):
        normalize_node_type("()")
    with pytest.raises(ValueError):
        normalize_node_type("}{}")


def test_node_type_strips_invalid_chars_and_normalizes():
    """Invalid chars stripped, remaining text normalized to PascalCase."""
    assert normalize_node_type("Constraint!Science") == "ConstraintScience"


def test_node_type_valid_pascal_case():
    assert normalize_node_type("DataStore") == "DataStore"
    assert normalize_node_type("tool") == "Tool"
    assert normalize_node_type("data_store") == "DataStore"


def test_node_type_empty_string_raises():
    with pytest.raises(ValueError):
        normalize_node_type("")
    with pytest.raises(ValueError):
        normalize_node_type("   ")


# --- normalize_edge_type: invalid character rejection ---


def test_edge_type_strips_json_corruption():
    """Invalid chars like { are stripped; valid remainder passes through."""
    assert normalize_edge_type("RELATES{TO") == "RELATESTO"


def test_edge_type_valid_screaming_snake():
    assert normalize_edge_type("RELATES_TO") == "RELATES_TO"
    assert normalize_edge_type("relates to") == "RELATES_TO"
    assert normalize_edge_type("relatesTo") == "RELATES_TO"


def test_edge_type_hyphen_preserved():
    """Hyphens are converted to underscores, so RELATES-TO works."""
    assert normalize_edge_type("RELATES-TO") == "RELATES_TO"


def test_edge_type_empty_after_strip_raises():
    with pytest.raises(ValueError):
        normalize_edge_type("{}")
    with pytest.raises(ValueError):
        normalize_edge_type("")


# --- names_are_similar ---


@pytest.mark.parametrize(
    "a, b, expected",
    [
        # Exact match (case-insensitive)
        ("DataForge", "DataForge", True),
        ("dataforge", "DataForge", True),
        # Multi-word containment (shorter has 2+ words)
        ("John Doe", "Doe John", True),
        # Single-word containment is intentionally rejected to avoid
        # false positives like "Serotonin" matching "Serotonin Receptor".
        # PG adapter uses trigram similarity for these cases instead.
        ("Kafka", "Apache Kafka", False),
        ("Team Atlas", "Atlas", False),
        # Not similar
        ("Alice", "Bob", False),
        ("Python", "JavaScript", False),
    ],
)
def test_names_are_similar(a: str, b: str, expected: bool) -> None:
    assert names_are_similar(a, b) == expected
