import argparse
from collections.abc import Sequence
from pathlib import Path

from pydantic_agents_playground.pipeline import run_demo

DEFAULT_DB_PATH = "data/pydantic_agents_playground.sqlite"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the Pydantic AI BMW ontology demo.")
    parser.add_argument("--db-path", default=DEFAULT_DB_PATH, help="Path to the SQLite database file.")
    parser.add_argument("--reset-db", action="store_true", help="Clear existing tables before processing messages.")
    parser.add_argument("--use-test-model", action="store_true", help="Use TestModel instead of Gemini.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.db_path != ":memory:":
        Path(args.db_path).parent.mkdir(parents=True, exist_ok=True)

    summary = run_demo(
        db_path=args.db_path,
        use_test_model=args.use_test_model,
        reset_db=args.reset_db,
    )

    print(f"Processed {summary.processed_messages} messages into {summary.db_path}")
    for table_name, count in summary.row_counts.items():
        print(f"{table_name}: {count}")

    return 0
