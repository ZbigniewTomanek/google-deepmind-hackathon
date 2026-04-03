"""One-shot ontology cleanup for existing graphs (Plan 28, Stage 6).

Fixes broken types produced before the ontology alignment pipeline improvements:
  a) Removes tool-call artifact types (Gemini Flash function-call leakage)
  b) Merges instance-level types into base types
  c) Merges redundant/overlapping types
  d) Deletes zero-usage edge types not in the seed ontology

Usage:
  uv run python scripts/cleanup_ontology.py                 # dry-run, all schemas
  uv run python scripts/cleanup_ontology.py --apply          # apply changes
  uv run python scripts/cleanup_ontology.py --schema ncx_alice__personal  # single schema
"""

from __future__ import annotations

import argparse
import asyncio

import asyncpg

from neocortex.config import PostgresConfig

# ── Seed types (from 003 + 006 migrations) — never delete ─────────────

SEED_NODE_TYPES: frozenset[str] = frozenset(
    {
        "Concept",
        "Person",
        "Document",
        "Event",
        "Tool",
        "Preference",
        "Organization",
        "Location",
        "Project",
        "Activity",
        "Asset",
        "Substance",
        "Metric",
        "Symptom",
        "Goal",
        "Task",
        "Emotion",
        "Recipe",
        "Protocol",
        "Routine",
    }
)

SEED_EDGE_TYPES: frozenset[str] = frozenset(
    {
        "RELATES_TO",
        "MENTIONS",
        "CAUSED_BY",
        "FOLLOWS",
        "AUTHORED",
        "USES",
        "CONTRADICTS",
        "SUPPORTS",
        "SUMMARIZES",
        "DERIVED_FROM",
        "SUPERSEDES",
        "CORRECTS",
        "HAS_GOAL",
        "WORKS_ON",
        "WORKS_FOR",
        "LOCATED_AT",
        "PART_OF",
        "EXPERIENCED",
        "CONSUMES",
        "PERFORMS",
        "OWNS",
        "RECOMMENDS",
        "IMPROVES",
    }
)

# ── Instance-level type merge map ──────────────────────────────────────

INSTANCE_TO_BASE: dict[str, str | None] = {
    "DishGreg": "Dish",
    "AssetSnowboardguards": "Asset",
    "AssetTires": "Asset",
    "AssetKiteboardingGear": "Asset",
    "DreamAiPresentation": "Dream",
    "DreamParaguayArtillery": "Dream",
    "LocationSalCapeVerde": "Location",
    "DeviceMacMiniServer": "Device",
    "InsightEngineKnock": "Insight",
    "InsightSubstanceOverstimulation": "Insight",
}

# ── Redundant type merge map ──────────────────────────────────────────

MERGE_REDUNDANT: dict[str, str] = {
    "AnatomicalLocation": "BodyPart",
    "AnatomicalStructure": "BodyPart",
    "HealthActivity": "Activity",
    "SportActivity": "Activity",
    "ArchitecturePatternProgrammingModel": "ArchitecturePattern",
    "ArchitectureConcept": "Concept",
    "TechnicalArchitecture": "ArchitecturePattern",
    "HealthState": "Symptom",
    "Condition": "Symptom",
}

# ── Schema discovery ──────────────────────────────────────────────────


async def get_graph_schemas(conn: asyncpg.Connection, target_schema: str | None) -> list[str]:
    """Get all ncx_ graph schemas from the registry."""
    if target_schema:
        row = await conn.fetchrow(
            "SELECT schema_name FROM graph_registry WHERE schema_name = $1",
            target_schema,
        )
        if row is None:
            print(f"  [ERROR] Schema '{target_schema}' not found in graph_registry")
            return []
        return [target_schema]

    rows = await conn.fetch("SELECT schema_name FROM graph_registry ORDER BY schema_name")
    return [r["schema_name"] for r in rows]


# ── Helpers ───────────────────────────────────────────────────────────


def _q(identifier: str) -> str:
    """Quote a SQL identifier (schema name)."""
    return '"' + identifier.replace('"', '""') + '"'


async def _get_type_id_by_name(conn: asyncpg.Connection, schema: str, table: str, name: str) -> int | None:
    """Look up a type ID by name."""
    row = await conn.fetchrow(f"SELECT id FROM {_q(schema)}.{table} WHERE name = $1", name)
    return row["id"] if row else None


async def _ensure_type_exists(conn: asyncpg.Connection, schema: str, table: str, name: str, description: str) -> int:
    """Ensure a type exists, creating it if needed. Returns the type ID."""
    type_id = await _get_type_id_by_name(conn, schema, table, name)
    if type_id is not None:
        return type_id
    row = await conn.fetchrow(
        f"INSERT INTO {_q(schema)}.{table} (name, description) VALUES ($1, $2) "
        f"ON CONFLICT (name) DO UPDATE SET name = EXCLUDED.name RETURNING id",
        name,
        description,
    )
    return row["id"]


# Tool-call artifact pattern for SQL regex matching
_ARTIFACT_PATTERN = (
    "(functiondefault|calldefault|ApicreateOr|UpdateNode" "|UpdateEdge|createOrUpdate|defaultApi|endcall)"
)

# ── Cleanup operations ────────────────────────────────────────────────


async def cleanup_tool_artifacts(conn: asyncpg.Connection, schema: str, dry_run: bool) -> dict[str, int]:
    """Remove types that contain tool-call artifact patterns."""
    stats = {"node_types_removed": 0, "edge_types_removed": 0, "nodes_reassigned": 0}
    qs = _q(schema)

    # Node types with artifacts
    artifact_node_types = await conn.fetch(f"SELECT id, name FROM {qs}.node_type WHERE name ~* '{_ARTIFACT_PATTERN}'")
    if artifact_node_types:
        concept_id = await _ensure_type_exists(conn, schema, "node_type", "Concept", "Abstract idea or topic")
        for row in artifact_node_types:
            node_count = await conn.fetchval(f"SELECT count(*) FROM {qs}.node WHERE type_id = $1", row["id"])
            if dry_run:
                print(
                    f"    [DRY-RUN] Would reassign {node_count} nodes from '{row['name']}' -> 'Concept' and delete type"
                )
            else:
                await conn.execute(
                    f"UPDATE {qs}.node SET type_id = $1 WHERE type_id = $2",
                    concept_id,
                    row["id"],
                )
                await conn.execute(f"DELETE FROM {qs}.node_type WHERE id = $1", row["id"])
                print(f"    Reassigned {node_count} nodes from '{row['name']}' -> 'Concept', deleted type")
            stats["nodes_reassigned"] += node_count
            stats["node_types_removed"] += 1

    # Edge types with artifacts
    artifact_edge_types = await conn.fetch(f"SELECT id, name FROM {qs}.edge_type WHERE name ~* '{_ARTIFACT_PATTERN}'")
    if artifact_edge_types:
        relates_to_id = await _ensure_type_exists(conn, schema, "edge_type", "RELATES_TO", "General relationship")
        for row in artifact_edge_types:
            edge_count = await conn.fetchval(f"SELECT count(*) FROM {qs}.edge WHERE type_id = $1", row["id"])
            if dry_run:
                print(
                    f"    [DRY-RUN] Would reassign {edge_count} edges"
                    f" from '{row['name']}' -> 'RELATES_TO' and delete type"
                )
            else:
                await conn.execute(
                    f"UPDATE {qs}.edge SET type_id = $1 WHERE type_id = $2",
                    relates_to_id,
                    row["id"],
                )
                await conn.execute(f"DELETE FROM {qs}.edge_type WHERE id = $1", row["id"])
                print(f"    Reassigned {edge_count} edges from '{row['name']}' -> 'RELATES_TO', deleted type")
            stats["edge_types_removed"] += 1

    return stats


async def merge_instance_types(conn: asyncpg.Connection, schema: str, dry_run: bool) -> dict[str, int]:
    """Merge instance-level types into their base types."""
    stats = {"types_merged": 0, "nodes_reassigned": 0}
    qs = _q(schema)

    for instance_name, base_name in INSTANCE_TO_BASE.items():
        source_id = await _get_type_id_by_name(conn, schema, "node_type", instance_name)
        if source_id is None:
            continue

        if base_name is None:
            # Delete with no merge target — reassign to Concept
            base_name = "Concept"

        target_id = await _ensure_type_exists(
            conn,
            schema,
            "node_type",
            base_name,
            f"Base type for {instance_name}",
        )

        node_count = await conn.fetchval(f"SELECT count(*) FROM {qs}.node WHERE type_id = $1", source_id)

        if dry_run:
            print(f"    [DRY-RUN] Would merge '{instance_name}' ({node_count} nodes) -> '{base_name}'")
        else:
            await conn.execute(
                f"UPDATE {qs}.node SET type_id = $1 WHERE type_id = $2",
                target_id,
                source_id,
            )
            await conn.execute(f"DELETE FROM {qs}.node_type WHERE id = $1", source_id)
            print(f"    Merged '{instance_name}' ({node_count} nodes) -> '{base_name}'")

        stats["types_merged"] += 1
        stats["nodes_reassigned"] += node_count

    return stats


async def merge_redundant_types(conn: asyncpg.Connection, schema: str, dry_run: bool) -> dict[str, int]:
    """Merge redundant/overlapping types."""
    stats = {"types_merged": 0, "nodes_reassigned": 0}
    qs = _q(schema)

    for source_name, target_name in MERGE_REDUNDANT.items():
        source_id = await _get_type_id_by_name(conn, schema, "node_type", source_name)
        if source_id is None:
            continue

        target_id = await _ensure_type_exists(
            conn,
            schema,
            "node_type",
            target_name,
            f"Canonical type (merged from {source_name})",
        )

        node_count = await conn.fetchval(f"SELECT count(*) FROM {qs}.node WHERE type_id = $1", source_id)

        if dry_run:
            print(f"    [DRY-RUN] Would merge '{source_name}' ({node_count} nodes) -> '{target_name}'")
        else:
            await conn.execute(
                f"UPDATE {qs}.node SET type_id = $1 WHERE type_id = $2",
                target_id,
                source_id,
            )
            await conn.execute(f"DELETE FROM {qs}.node_type WHERE id = $1", source_id)
            print(f"    Merged '{source_name}' ({node_count} nodes) -> '{target_name}'")

        stats["types_merged"] += 1
        stats["nodes_reassigned"] += node_count

    return stats


async def cleanup_unused_edge_types(conn: asyncpg.Connection, schema: str, dry_run: bool) -> dict[str, int]:
    """Delete edge types with 0 edges that are not in the seed ontology."""
    stats = {"edge_types_removed": 0}
    qs = _q(schema)

    unused = await conn.fetch(f"""SELECT et.id, et.name
            FROM {qs}.edge_type et
            LEFT JOIN {qs}.edge e ON e.type_id = et.id
            WHERE e.id IS NULL
            ORDER BY et.name""")

    for row in unused:
        if row["name"] in SEED_EDGE_TYPES:
            continue

        if dry_run:
            print(f"    [DRY-RUN] Would delete unused edge type '{row['name']}'")
        else:
            await conn.execute(f"DELETE FROM {qs}.edge_type WHERE id = $1", row["id"])
            print(f"    Deleted unused edge type '{row['name']}'")

        stats["edge_types_removed"] += 1

    return stats


# ── Schema summary ────────────────────────────────────────────────────


async def print_schema_summary(conn: asyncpg.Connection, schema: str, label: str) -> None:
    """Print type counts for a schema."""
    qs = _q(schema)

    node_type_count = await conn.fetchval(f"SELECT count(*) FROM {qs}.node_type")
    edge_type_count = await conn.fetchval(f"SELECT count(*) FROM {qs}.edge_type")
    node_count = await conn.fetchval(f"SELECT count(*) FROM {qs}.node")
    edge_count = await conn.fetchval(f"SELECT count(*) FROM {qs}.edge")

    active_node_types = await conn.fetchval(f"""SELECT count(DISTINCT nt.id)
            FROM {qs}.node_type nt
            JOIN {qs}.node n ON n.type_id = nt.id""")
    active_edge_types = await conn.fetchval(f"""SELECT count(DISTINCT et.id)
            FROM {qs}.edge_type et
            JOIN {qs}.edge e ON e.type_id = et.id""")

    print(f"  [{label}] {schema}:")
    print(f"    Nodes: {node_count}, Edge: {edge_count}")
    print(f"    Node types: {node_type_count} (active: {active_node_types})")
    print(f"    Edge types: {edge_type_count} (active: {active_edge_types})")
    unused_edge_pct = round((edge_type_count - active_edge_types) / edge_type_count * 100) if edge_type_count > 0 else 0
    print(f"    Unused edge types: {unused_edge_pct}%")


# ── Main ──────────────────────────────────────────────────────────────


async def cleanup_schema(conn: asyncpg.Connection, schema: str, dry_run: bool) -> dict[str, int]:
    """Run all cleanup operations on a single schema within a transaction."""
    totals: dict[str, int] = {}

    print(f"\n{'='*60}")
    print(f"Schema: {schema} ({'DRY RUN' if dry_run else 'APPLYING'})")
    print(f"{'='*60}")

    await print_schema_summary(conn, schema, "BEFORE")

    print("\n  --- Tool-call artifact cleanup ---")
    stats = await cleanup_tool_artifacts(conn, schema, dry_run)
    for k, v in stats.items():
        totals[k] = totals.get(k, 0) + v

    print("\n  --- Instance-level type merge ---")
    stats = await merge_instance_types(conn, schema, dry_run)
    for k, v in stats.items():
        totals[k] = totals.get(k, 0) + v

    print("\n  --- Redundant type merge ---")
    stats = await merge_redundant_types(conn, schema, dry_run)
    for k, v in stats.items():
        totals[k] = totals.get(k, 0) + v

    print("\n  --- Unused edge type cleanup ---")
    stats = await cleanup_unused_edge_types(conn, schema, dry_run)
    for k, v in stats.items():
        totals[k] = totals.get(k, 0) + v

    if not dry_run:
        print()
        await print_schema_summary(conn, schema, "AFTER")

    return totals


async def main() -> None:
    parser = argparse.ArgumentParser(description="Cleanup broken ontology types in existing NeoCortex graphs")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Preview changes without applying (default)",
    )
    mode.add_argument(
        "--apply",
        action="store_true",
        help="Apply changes to the database",
    )
    parser.add_argument(
        "--schema",
        type=str,
        default=None,
        help="Target a specific schema (default: all ncx_ schemas)",
    )
    args = parser.parse_args()

    dry_run = not args.apply

    config = PostgresConfig()
    conn = await asyncpg.connect(config.dsn)

    try:
        schemas = await get_graph_schemas(conn, args.schema)
        if not schemas:
            print("No graph schemas found.")
            return

        print(f"Found {len(schemas)} graph schema(s): {', '.join(schemas)}")
        print(f"Mode: {'DRY RUN' if dry_run else 'APPLY'}")

        grand_totals: dict[str, int] = {}

        for schema in schemas:
            if dry_run:
                # Dry-run: no mutations, no transaction needed
                stats = await cleanup_schema(conn, schema, dry_run=True)
            else:
                # Apply: wrap each schema in its own transaction
                async with conn.transaction():
                    stats = await cleanup_schema(conn, schema, dry_run=False)
            for k, v in stats.items():
                grand_totals[k] = grand_totals.get(k, 0) + v

    finally:
        await conn.close()

    print(f"\n{'='*60}")
    print("GRAND TOTALS")
    print(f"{'='*60}")
    for k, v in sorted(grand_totals.items()):
        print(f"  {k}: {v}")


if __name__ == "__main__":
    asyncio.run(main())
