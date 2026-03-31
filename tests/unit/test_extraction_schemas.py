"""Unit tests for extraction schema validators (Plan 19, M4/M6)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from neocortex.extraction.schemas import ExtractedEntity, ProposedNodeType

# --- ProposedNodeType validators ---


def test_proposed_node_type_rejects_long_name() -> None:
    with pytest.raises(ValidationError):
        ProposedNodeType(name="x" * 61)


def test_proposed_node_type_rejects_lowercase_start() -> None:
    with pytest.raises(ValidationError):
        ProposedNodeType(name="lowercase")


def test_proposed_node_type_accepts_valid() -> None:
    t = ProposedNodeType(name="Algorithm", description="An algorithm")
    assert t.name == "Algorithm"


# --- ExtractedEntity temporal fields ---


def test_extracted_entity_temporal_fields() -> None:
    e = ExtractedEntity(
        name="Metaphone3 Hybrid",
        type_name="Algorithm",
        supersedes="Metaphone3",
        temporal_signal="SUPERSEDES",
    )
    assert e.supersedes == "Metaphone3"
    assert e.temporal_signal == "SUPERSEDES"


def test_extracted_entity_temporal_fields_default_none() -> None:
    e = ExtractedEntity(name="X", type_name="Y")
    assert e.supersedes is None
    assert e.temporal_signal is None


def test_extracted_entity_rejects_long_type_name() -> None:
    with pytest.raises(ValidationError):
        ExtractedEntity(name="Foo", type_name="A" * 61)


def test_extracted_entity_rejects_lowercase_type_name() -> None:
    with pytest.raises(ValidationError):
        ExtractedEntity(name="Foo", type_name="lowercase")
