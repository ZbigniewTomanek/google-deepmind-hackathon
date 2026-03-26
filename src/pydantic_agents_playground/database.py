import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from pydantic_agents_playground.schemas import (
    LibrarianPayload,
    OntologyClass,
    OntologyProperty,
    PersistedFact,
    PersistedFactMention,
    SeedMessage,
)


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


class SQLiteRepository:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        if db_path != ":memory:":
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(db_path)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> "SQLiteRepository":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    @contextmanager
    def transaction(self) -> Iterator[None]:
        try:
            self.connection.execute("BEGIN")
            yield
        except Exception:
            self.connection.rollback()
            raise
        else:
            self.connection.commit()

    def create_schema(self) -> None:
        self.connection.executescript("""
            CREATE TABLE IF NOT EXISTS messages (
                message_id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                topic TEXT NOT NULL,
                content TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS ontology_classes (
                class_id TEXT PRIMARY KEY,
                label TEXT NOT NULL,
                description TEXT NOT NULL,
                parent_class_id TEXT NULL
            );

            CREATE TABLE IF NOT EXISTS ontology_class_history (
                history_id INTEGER PRIMARY KEY AUTOINCREMENT,
                message_id TEXT NOT NULL,
                class_id TEXT NOT NULL,
                label TEXT NOT NULL,
                description TEXT NOT NULL,
                parent_class_id TEXT NULL,
                change_type TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS ontology_properties (
                property_id TEXT PRIMARY KEY,
                label TEXT NOT NULL,
                description TEXT NOT NULL,
                domain_class_id TEXT NOT NULL,
                value_type TEXT NOT NULL,
                range_class_id TEXT NULL,
                multi_valued INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS ontology_property_history (
                history_id INTEGER PRIMARY KEY AUTOINCREMENT,
                message_id TEXT NOT NULL,
                property_id TEXT NOT NULL,
                label TEXT NOT NULL,
                description TEXT NOT NULL,
                domain_class_id TEXT NOT NULL,
                value_type TEXT NOT NULL,
                range_class_id TEXT NULL,
                multi_valued INTEGER NOT NULL,
                change_type TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS entities (
                entity_id TEXT PRIMARY KEY,
                label TEXT NOT NULL,
                class_id TEXT NOT NULL,
                canonical_name TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS facts (
                fact_id TEXT PRIMARY KEY,
                subject_entity_id TEXT NOT NULL,
                property_id TEXT NOT NULL,
                value_type TEXT NOT NULL,
                string_value TEXT NULL,
                number_value REAL NULL,
                boolean_value INTEGER NULL,
                date_value TEXT NULL,
                target_entity_id TEXT NULL,
                fact_signature TEXT NOT NULL UNIQUE
            );

            CREATE TABLE IF NOT EXISTS fact_mentions (
                mention_id TEXT PRIMARY KEY,
                fact_id TEXT NOT NULL,
                source_message_id TEXT NOT NULL,
                evidence_text TEXT NOT NULL,
                confidence REAL NOT NULL,
                UNIQUE (fact_id, source_message_id, evidence_text)
            );

            CREATE TABLE IF NOT EXISTS processing_runs (
                run_id INTEGER PRIMARY KEY AUTOINCREMENT,
                message_id TEXT NOT NULL,
                new_class_count INTEGER NOT NULL,
                new_property_count INTEGER NOT NULL,
                entity_count INTEGER NOT NULL,
                canonical_fact_count INTEGER NOT NULL,
                fact_mention_count INTEGER NOT NULL,
                summary TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            """)
        self.connection.commit()

    def reset_database(self) -> None:
        table_names = (
            "fact_mentions",
            "facts",
            "entities",
            "ontology_property_history",
            "ontology_properties",
            "ontology_class_history",
            "ontology_classes",
            "processing_runs",
            "messages",
        )
        with self.transaction():
            for table_name in table_names:
                self.connection.execute(f"DELETE FROM {table_name}")

    def upsert_message(self, message: SeedMessage) -> None:
        self.connection.execute(
            """
            INSERT INTO messages (message_id, title, topic, content)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(message_id) DO UPDATE SET
                title = excluded.title,
                topic = excluded.topic,
                content = excluded.content
            """,
            (message.message_id, message.title, message.topic, message.content),
        )

    def load_ontology(self) -> tuple[list[OntologyClass], list[OntologyProperty]]:
        class_rows = self.connection.execute("""
            SELECT class_id, label, description, parent_class_id
            FROM ontology_classes
            ORDER BY class_id
            """).fetchall()
        property_rows = self.connection.execute("""
            SELECT property_id, label, description, domain_class_id, value_type, range_class_id, multi_valued
            FROM ontology_properties
            ORDER BY property_id
            """).fetchall()

        classes = [OntologyClass.model_validate(dict(row)) for row in class_rows]
        properties = [
            OntologyProperty.model_validate(
                {
                    **dict(row),
                    "multi_valued": bool(row["multi_valued"]),
                }
            )
            for row in property_rows
        ]
        return classes, properties

    def load_known_entity_ids(self) -> list[str]:
        rows = self.connection.execute("SELECT entity_id FROM entities ORDER BY entity_id").fetchall()
        return [row["entity_id"] for row in rows]

    def load_known_fact_signatures(self) -> list[str]:
        rows = self.connection.execute("SELECT fact_signature FROM facts ORDER BY fact_signature").fetchall()
        return [row["fact_signature"] for row in rows]

    def apply_librarian_payload(self, message_id: str, payload: LibrarianPayload) -> dict[str, int]:
        counts = {
            "accepted_classes": 0,
            "accepted_properties": 0,
            "entities": 0,
            "canonical_facts": 0,
            "fact_mentions": 0,
        }

        for ontology_class in payload.accepted_classes:
            counts["accepted_classes"] += self._insert_ontology_class(message_id, ontology_class)

        for ontology_property in payload.accepted_properties:
            counts["accepted_properties"] += self._insert_ontology_property(message_id, ontology_property)

        for entity in payload.entities_to_upsert:
            self.connection.execute(
                """
                INSERT INTO entities (entity_id, label, class_id, canonical_name)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(entity_id) DO UPDATE SET
                    label = excluded.label,
                    class_id = excluded.class_id,
                    canonical_name = excluded.canonical_name
                """,
                (entity.entity_id, entity.label, entity.class_id, entity.canonical_name),
            )
            counts["entities"] += 1

        fact_ids_by_signature: dict[str, str] = {}
        for fact in payload.canonical_facts_to_upsert:
            fact_signature = self.build_fact_signature(fact)
            fact_id, was_inserted = self._ensure_canonical_fact(fact, fact_signature)
            fact_ids_by_signature[fact_signature] = fact_id
            counts["canonical_facts"] += int(was_inserted)

        for mention in payload.fact_mentions_to_insert:
            fact_signature = self.build_fact_signature(mention)
            fact_id = fact_ids_by_signature.get(fact_signature) or self._load_fact_id_by_signature(fact_signature)
            if fact_id is None:
                raise ValueError(f"Cannot insert fact mention without canonical fact: {fact_signature}")
            counts["fact_mentions"] += self._insert_fact_mention(fact_id, mention)

        return counts

    def record_processing_run(
        self,
        message_id: str,
        new_class_count: int,
        new_property_count: int,
        entity_count: int,
        canonical_fact_count: int,
        fact_mention_count: int,
        summary: str,
    ) -> None:
        self.connection.execute(
            """
            INSERT INTO processing_runs (
                message_id,
                new_class_count,
                new_property_count,
                entity_count,
                canonical_fact_count,
                fact_mention_count,
                summary,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                message_id,
                new_class_count,
                new_property_count,
                entity_count,
                canonical_fact_count,
                fact_mention_count,
                summary,
                _utc_now(),
            ),
        )

    def build_fact_signature(self, fact: PersistedFact | PersistedFactMention) -> str:
        normalized_value: str | float | bool | None
        if fact.value_type == "entity":
            normalized_value = fact.target_entity_id
        elif fact.value_type == "number":
            normalized_value = None if fact.number_value is None else float(f"{fact.number_value:.15g}")
        elif fact.value_type == "boolean":
            normalized_value = fact.boolean_value
        elif fact.value_type == "date":
            normalized_value = None if fact.date_value is None else fact.date_value.strip()
        else:
            normalized_value = None if fact.string_value is None else fact.string_value.strip()

        return json.dumps(
            [fact.subject_entity_id, fact.property_id, fact.value_type, normalized_value],
            sort_keys=False,
            separators=(",", ":"),
        )

    def count_rows(self, table_name: str) -> int:
        row = self.connection.execute(f"SELECT COUNT(*) AS count FROM {table_name}").fetchone()
        if row is None:
            return 0
        return int(row["count"])

    def _insert_ontology_class(self, message_id: str, ontology_class: OntologyClass) -> int:
        cursor = self.connection.execute(
            """
            INSERT OR IGNORE INTO ontology_classes (class_id, label, description, parent_class_id)
            VALUES (?, ?, ?, ?)
            """,
            (
                ontology_class.class_id,
                ontology_class.label,
                ontology_class.description,
                ontology_class.parent_class_id,
            ),
        )
        if cursor.rowcount:
            self.connection.execute(
                """
                INSERT INTO ontology_class_history (
                    message_id,
                    class_id,
                    label,
                    description,
                    parent_class_id,
                    change_type,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    message_id,
                    ontology_class.class_id,
                    ontology_class.label,
                    ontology_class.description,
                    ontology_class.parent_class_id,
                    "accepted_addition",
                    _utc_now(),
                ),
            )
            return 1
        return 0

    def _insert_ontology_property(self, message_id: str, ontology_property: OntologyProperty) -> int:
        cursor = self.connection.execute(
            """
            INSERT OR IGNORE INTO ontology_properties (
                property_id,
                label,
                description,
                domain_class_id,
                value_type,
                range_class_id,
                multi_valued
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ontology_property.property_id,
                ontology_property.label,
                ontology_property.description,
                ontology_property.domain_class_id,
                ontology_property.value_type,
                ontology_property.range_class_id,
                int(ontology_property.multi_valued),
            ),
        )
        if cursor.rowcount:
            self.connection.execute(
                """
                INSERT INTO ontology_property_history (
                    message_id,
                    property_id,
                    label,
                    description,
                    domain_class_id,
                    value_type,
                    range_class_id,
                    multi_valued,
                    change_type,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    message_id,
                    ontology_property.property_id,
                    ontology_property.label,
                    ontology_property.description,
                    ontology_property.domain_class_id,
                    ontology_property.value_type,
                    ontology_property.range_class_id,
                    int(ontology_property.multi_valued),
                    "accepted_addition",
                    _utc_now(),
                ),
            )
            return 1
        return 0

    def _ensure_canonical_fact(self, fact: PersistedFact, fact_signature: str) -> tuple[str, bool]:
        fact_id = f"fact-{uuid5(NAMESPACE_URL, fact_signature)}"
        cursor = self.connection.execute(
            """
            INSERT OR IGNORE INTO facts (
                fact_id,
                subject_entity_id,
                property_id,
                value_type,
                string_value,
                number_value,
                boolean_value,
                date_value,
                target_entity_id,
                fact_signature
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                fact_id,
                fact.subject_entity_id,
                fact.property_id,
                fact.value_type,
                fact.string_value,
                fact.number_value,
                None if fact.boolean_value is None else int(fact.boolean_value),
                fact.date_value,
                fact.target_entity_id,
                fact_signature,
            ),
        )
        return fact_id, bool(cursor.rowcount)

    def _insert_fact_mention(self, fact_id: str, mention: PersistedFactMention) -> int:
        mention_key = json.dumps([fact_id, mention.source_message_id, mention.evidence_text], separators=(",", ":"))
        mention_id = f"mention-{uuid5(NAMESPACE_URL, mention_key)}"
        cursor = self.connection.execute(
            """
            INSERT OR IGNORE INTO fact_mentions (
                mention_id,
                fact_id,
                source_message_id,
                evidence_text,
                confidence
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (mention_id, fact_id, mention.source_message_id, mention.evidence_text, mention.confidence),
        )
        return 1 if cursor.rowcount else 0

    def _load_fact_id_by_signature(self, fact_signature: str) -> str | None:
        row = self.connection.execute(
            "SELECT fact_id FROM facts WHERE fact_signature = ?",
            (fact_signature,),
        ).fetchone()
        if row is None:
            return None
        return str(row["fact_id"])
