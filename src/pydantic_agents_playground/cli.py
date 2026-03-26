import argparse
from collections.abc import Sequence
from pathlib import Path

from loguru import logger

from pydantic_agents_playground.database import SQLiteRepository
from pydantic_agents_playground.logging import configure_logging
from pydantic_agents_playground.pipeline import run_demo

DEFAULT_DB_PATH = "data/pydantic_agents_playground.sqlite"
DEFAULT_MESSAGE_LIMIT = 5


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Inspect or run the Pydantic AI BMW ontology demo.")
    parser.add_argument("--db-path", default=DEFAULT_DB_PATH, help="Path to the SQLite database file.")
    parser.add_argument("--reset-db", action="store_true", help="Clear existing tables before processing messages.")
    parser.add_argument("--use-test-model", action="store_true", help="Use TestModel instead of Gemini.")
    parser.add_argument(
        "--message-limit",
        type=int,
        default=DEFAULT_MESSAGE_LIMIT,
        help="Maximum number of seed messages to process.",
    )
    parser.add_argument(
        "--run-demo",
        action="store_true",
        help="Execute the agent pipeline before printing the persisted state.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    configure_logging()
    args = build_parser().parse_args(argv)
    logger.info(
        "CLI invocation db_path={} reset_db={} use_test_model={} message_limit={} run_demo={}",
        args.db_path,
        args.reset_db,
        args.use_test_model,
        args.message_limit,
        args.run_demo,
    )
    if args.db_path != ":memory:":
        Path(args.db_path).parent.mkdir(parents=True, exist_ok=True)

    if args.run_demo:
        summary = run_demo(
            db_path=args.db_path,
            use_test_model=args.use_test_model,
            reset_db=args.reset_db,
            message_limit=args.message_limit,
        )

        print(f"Processed {summary.processed_messages} messages into {summary.db_path}")
        for table_name, count in summary.row_counts.items():
            print(f"{table_name}: {count}")
        print()
    print(render_database_state(args.db_path))

    return 0


def render_database_state(db_path: str) -> str:
    with SQLiteRepository(db_path) as repo:
        repo.create_schema()
        classes, properties = repo.load_ontology()
        entities = repo.load_entities()
        fact_rows = repo.load_canonical_fact_rows()

    entity_names = {entity.entity_id: entity.canonical_name for entity in entities}
    property_labels = {ontology_property.property_id: ontology_property.label for ontology_property in properties}

    lines = [
        "Ontology Classes",
        *(_format_ontology_classes(classes) or ["- none"]),
        "",
        "Ontology Properties",
        *(_format_ontology_properties(properties) or ["- none"]),
        "",
        "Known Facts",
        *(_format_known_facts(fact_rows, entity_names, property_labels) or ["- none"]),
    ]
    return "\n".join(lines)


def _format_ontology_classes(classes) -> list[str]:
    return [
        (
            f"- {ontology_class.class_id}: {ontology_class.label}"
            + (f" [parent={ontology_class.parent_class_id}]" if ontology_class.parent_class_id else "")
            + f" | {ontology_class.description}"
        )
        for ontology_class in classes
    ]


def _format_ontology_properties(properties) -> list[str]:
    lines: list[str] = []
    for ontology_property in properties:
        range_part = (
            f" -> {ontology_property.range_class_id}"
            if ontology_property.value_type == "entity" and ontology_property.range_class_id
            else ""
        )
        multivalue_part = " [multi]" if ontology_property.multi_valued else ""
        lines.append(
            f"- {ontology_property.property_id}: {ontology_property.domain_class_id} -> "
            f"{ontology_property.value_type}{range_part}{multivalue_part} | {ontology_property.description}"
        )
    return lines


def _format_known_facts(
    fact_rows: list[dict[str, object]],
    entity_names: dict[str, str],
    property_labels: dict[str, str],
) -> list[str]:
    lines: list[str] = []
    for row in fact_rows:
        subject_entity_id = str(row["subject_entity_id"])
        property_id = str(row["property_id"])
        value_type = str(row["value_type"])
        mention_count_value = row["mention_count"]
        if mention_count_value is None:
            mention_count = 0
        elif isinstance(mention_count_value, int):
            mention_count = mention_count_value
        elif isinstance(mention_count_value, float):
            mention_count = int(mention_count_value)
        else:
            mention_count = int(str(mention_count_value))
        subject = entity_names.get(subject_entity_id, subject_entity_id)
        property_label = property_labels.get(property_id, property_id)
        value = _format_fact_value(row, entity_names, value_type)
        lines.append(
            f"- {subject} ({subject_entity_id}) | {property_label} ({property_id}) | {value} | mentions={mention_count}"
        )
    return lines


def _format_fact_value(
    fact_row: dict[str, object],
    entity_names: dict[str, str],
    value_type: str,
) -> str:
    if value_type == "entity":
        target_entity_id = fact_row["target_entity_id"]
        if target_entity_id is None:
            return "missing-target"
        target_entity_id = str(target_entity_id)
        target_name = entity_names.get(target_entity_id, target_entity_id)
        return f"{target_name} ({target_entity_id})"
    if value_type == "number":
        return str(fact_row["number_value"])
    if value_type == "boolean":
        return str(bool(fact_row["boolean_value"]))
    if value_type == "date":
        return str(fact_row["date_value"] or "missing-date")
    return str(fact_row["string_value"] or "missing-string")
