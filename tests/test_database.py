from pydantic_agents_playground.database import SQLiteRepository
from pydantic_agents_playground.messages import SEED_MESSAGES
from pydantic_agents_playground.schemas import (
    LibrarianPayload,
    OntologyClass,
    OntologyProperty,
    PersistedEntity,
    PersistedFact,
    PersistedFactMention,
)


def test_seed_messages_include_expected_corpus_size() -> None:
    assert len(SEED_MESSAGES) == 10
    assert SEED_MESSAGES[0].message_id == "msg-001"
    assert SEED_MESSAGES[-1].message_id == "msg-010"


def test_repository_persists_ontology_history_and_deduplicated_facts() -> None:
    with SQLiteRepository(":memory:") as repo:
        repo.create_schema()

        payload = LibrarianPayload(
            accepted_classes=[
                OntologyClass(
                    class_id="car_model",
                    label="Car Model",
                    description="A named vehicle model.",
                )
            ],
            accepted_properties=[
                OntologyProperty(
                    property_id="has_body_style",
                    label="has body style",
                    description="Links a car model to a body style.",
                    domain_class_id="car_model",
                    value_type="string",
                )
            ],
            entities_to_upsert=[
                PersistedEntity(
                    entity_id="bmw_320d",
                    label="BMW 320d",
                    class_id="car_model",
                    canonical_name="BMW 320d",
                )
            ],
            canonical_facts_to_upsert=[
                PersistedFact(
                    subject_entity_id="bmw_320d",
                    property_id="has_body_style",
                    value_type="string",
                    string_value="Touring",
                )
            ],
            fact_mentions_to_insert=[
                PersistedFactMention(
                    subject_entity_id="bmw_320d",
                    property_id="has_body_style",
                    value_type="string",
                    string_value="Touring",
                    source_message_id="msg-007",
                    evidence_text="BMW has long offered Touring versions",
                    confidence=0.93,
                ),
                PersistedFactMention(
                    subject_entity_id="bmw_320d",
                    property_id="has_body_style",
                    value_type="string",
                    string_value="Touring",
                    source_message_id="msg-007",
                    evidence_text="BMW has long offered Touring versions",
                    confidence=0.93,
                ),
            ],
            summary="Repository smoke test.",
        )

        with repo.transaction():
            repo.upsert_message(SEED_MESSAGES[6])
            counts = repo.apply_librarian_payload("msg-007", payload)
            repo.record_processing_run(
                message_id="msg-007",
                new_class_count=counts["accepted_classes"],
                new_property_count=counts["accepted_properties"],
                entity_count=counts["entities"],
                canonical_fact_count=counts["canonical_facts"],
                fact_mention_count=counts["fact_mentions"],
                summary=payload.summary,
            )

        classes, properties = repo.load_ontology()

        assert counts == {
            "accepted_classes": 1,
            "accepted_properties": 1,
            "entities": 1,
            "canonical_facts": 1,
            "fact_mentions": 1,
        }
        assert [item.class_id for item in classes] == ["car_model"]
        assert [item.property_id for item in properties] == ["has_body_style"]
        assert repo.load_known_entity_ids() == ["bmw_320d"]
        assert len(repo.load_known_fact_signatures()) == 1
        assert repo.count_rows("ontology_class_history") == 1
        assert repo.count_rows("ontology_property_history") == 1
        assert repo.count_rows("facts") == 1
        assert repo.count_rows("fact_mentions") == 1
        assert repo.count_rows("processing_runs") == 1

        with repo.transaction():
            counts_second_pass = repo.apply_librarian_payload("msg-007", payload)

        assert counts_second_pass["accepted_classes"] == 0
        assert counts_second_pass["accepted_properties"] == 0
        assert counts_second_pass["canonical_facts"] == 0
        assert counts_second_pass["fact_mentions"] == 0
