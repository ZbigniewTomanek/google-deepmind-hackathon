from pydantic_agents_playground.cli import main
from pydantic_agents_playground.pipeline import _normalize_librarian_payload, run_demo
from pydantic_agents_playground.schemas import (
    LibrarianPayload,
    PersistedEntity,
    PersistedFactMention,
)


def test_run_demo_processes_all_seed_messages_with_test_model(tmp_path, capsys) -> None:
    db_path = tmp_path / "demo.sqlite"

    summary = run_demo(str(db_path), use_test_model=True, reset_db=True)
    captured = capsys.readouterr()

    assert summary.processed_messages == 5
    assert summary.db_path == str(db_path)
    assert summary.row_counts["messages"] == 5
    assert summary.row_counts["processing_runs"] == 5
    assert "msg-001 classes=0 properties=0 canonical_facts=0 mentions=0" in captured.out
    assert "msg-005 classes=0 properties=0 canonical_facts=0 mentions=0" in captured.out


def test_cli_main_runs_demo_and_prints_final_summary(tmp_path, capsys) -> None:
    db_path = tmp_path / "cli-demo.sqlite"

    exit_code = main(["--db-path", str(db_path), "--use-test-model", "--reset-db", "--run-demo"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert db_path.exists()
    assert "Processed 5 messages into" in captured.out
    assert "processing_runs: 5" in captured.out
    assert "Ontology Classes" in captured.out


def test_cli_prints_state_without_running_demo(tmp_path, capsys) -> None:
    db_path = tmp_path / "cli-demo.sqlite"
    db_path.touch()

    exit_code = main(["--db-path", str(db_path)])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "Ontology Classes" in captured.out
    assert "Ontology Properties" in captured.out
    assert "Known Facts" in captured.out
    assert "- none" in captured.out
    assert "Processed" not in captured.out


def test_normalize_librarian_payload_derives_missing_canonical_facts_from_mentions() -> None:
    payload = LibrarianPayload(
        entities_to_upsert=[
            PersistedEntity(
                entity_id="e36",
                label="BMW 3 Series E36",
                class_id="generation",
                canonical_name="BMW 3 Series E36",
            )
        ],
        canonical_facts_to_upsert=[],
        fact_mentions_to_insert=[
            PersistedFactMention(
                subject_entity_id="e36",
                property_id="belongs_to_model",
                value_type="entity",
                target_entity_id="bmw_3_series",
                source_message_id="msg-003",
                evidence_text="During the E36 and E46 era...",
                confidence=1.0,
            )
        ],
        summary="Payload repair test.",
    )

    normalized = _normalize_librarian_payload(
        payload,
        accepted_classes=[],
        accepted_properties=[],
    )

    assert len(normalized.canonical_facts_to_upsert) == 1
    assert normalized.canonical_facts_to_upsert[0].subject_entity_id == "e36"
    assert normalized.canonical_facts_to_upsert[0].property_id == "belongs_to_model"
    assert normalized.canonical_facts_to_upsert[0].target_entity_id == "bmw_3_series"
