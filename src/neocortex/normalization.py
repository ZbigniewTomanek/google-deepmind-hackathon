"""Entity name and type normalization utilities.

These functions are called in the adapter layer BEFORE database lookups,
ensuring consistent matching regardless of how the LLM formats names.
"""

from __future__ import annotations

import re

_KNOWN_ACRONYMS: list[str] = [
    "API",
    "SQL",
    "AI",
    "ML",
    "LLM",
    "HTTP",
    "REST",
    "gRPC",
    "OAuth",
    "SSO",
    "JWT",
    "5-HT",
]


def canonicalize_name(name: str) -> tuple[str, list[str]]:
    """Normalize an entity name and extract any parenthetical aliases.

    Returns (canonical_name, aliases).
    """
    # 1. Strip whitespace
    name = name.strip()
    if not name:
        return (name, [])

    # 2. Extract parenthetical aliases (single parenthetical at end)
    aliases: list[str] = []
    m = re.match(r"^(.+?)\s*\(([^)]+)\)\s*$", name)
    if m:
        name = m.group(1).strip()
        aliases.append(m.group(2).strip())

    # 3. Title case normalization — only when input is all-lowercase
    if name == name.lower():
        name = name.title()
        # Restore known acronyms
        for acronym in _KNOWN_ACRONYMS:
            pattern = re.compile(re.escape(acronym), re.IGNORECASE)
            name = pattern.sub(acronym, name)

    # 4. Collapse internal whitespace
    name = re.sub(r"\s+", " ", name).strip()

    return (name, aliases)


def normalize_edge_type(name: str) -> str:
    """Convert any edge type name to SCREAMING_SNAKE_CASE."""
    # Replace hyphens with underscores
    name = name.replace("-", "_")
    # Insert underscore before uppercase letters preceded by lowercase or digit (PascalCase split)
    name = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", name)
    # Replace spaces with underscores
    name = name.replace(" ", "_")
    # Uppercase everything
    name = name.upper()
    # Collapse multiple underscores
    name = re.sub(r"_+", "_", name)
    # Strip leading/trailing underscores
    name = name.strip("_")
    return name


def normalize_node_type(name: str) -> str:
    """Ensure PascalCase for node type names."""
    # Check if it has separators (underscores or spaces)
    has_separators = "_" in name or " " in name

    if has_separators:
        # Split on separators and capitalize each part
        parts = re.split(r"[_ ]+", name)
        return "".join(part.capitalize() for part in parts if part)

    # No separators — check if it's all-caps single word
    if name == name.upper() and len(name) > 1:
        # ALL_CAPS single word with no separators → preserve as-is
        return name

    # Already PascalCase or mixed case → keep as-is
    return name


def names_are_similar(a: str, b: str, threshold: float = 0.6) -> bool:
    """Pure-Python string similarity check for use in the mock adapter.

    Checks exact match (case-insensitive), then word-level containment.
    Requires the shorter name to have at least 2 words to prevent
    false positives like "Serotonin" matching "Serotonin Receptor".

    For single-word containment (e.g., "Kafka" vs "Apache Kafka"),
    the PostgreSQL adapter uses trigram similarity instead. This function
    is intentionally conservative to avoid false merges in mock tests.
    """
    a_lower = a.lower()
    b_lower = b.lower()

    # 1. Exact match after lowering
    if a_lower == b_lower:
        return True

    # 2. Word-level containment: all words of shorter are in longer,
    #    but only when the shorter name has 2+ words to avoid false
    #    positives from single-word matches (e.g., "Serotonin" should
    #    NOT match "Serotonin Receptor")
    a_words = set(a_lower.split())
    b_words = set(b_lower.split())
    if not a_words or not b_words:
        return False

    shorter, longer = (a_words, b_words) if len(a_words) <= len(b_words) else (b_words, a_words)
    return bool(shorter <= longer and len(shorter) >= 2)
