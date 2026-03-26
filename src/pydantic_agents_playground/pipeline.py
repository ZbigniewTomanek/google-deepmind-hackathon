from collections.abc import Iterable

from pydantic_agents_playground.agents import (
    build_extractor_agent,
    build_librarian_agent,
    build_ontology_agent,
)
from pydantic_agents_playground.database import SQLiteRepository
from pydantic_agents_playground.messages import SEED_MESSAGES
from pydantic_agents_playground.schemas import (
    DemoRunSummary,
    ExtractorAgentDeps,
    LibrarianAgentDeps,
    LibrarianPayload,
    OntologyAgentDeps,
    OntologyClass,
    OntologyProperty,
)

SUMMARY_TABLES = (
    "messages",
    "ontology_classes",
    "ontology_properties",
    "ontology_class_history",
    "ontology_property_history",
    "entities",
    "facts",
    "fact_mentions",
    "processing_runs",
)


def run_demo(
    db_path: str,
    use_test_model: bool = False,
    reset_db: bool = False,
) -> DemoRunSummary:
    with SQLiteRepository(db_path) as repo:
        repo.create_schema()
        if reset_db:
            repo.reset_database()

        ontology_agent = build_ontology_agent(use_test_model=use_test_model)
        extractor_agent = build_extractor_agent(use_test_model=use_test_model)
        librarian_agent = build_librarian_agent(use_test_model=use_test_model)

        for message in SEED_MESSAGES:
            existing_classes, existing_properties = repo.load_ontology()

            ontology_result = ontology_agent.run_sync(
                "Review the current message and propose conservative ontology additions.",
                deps=OntologyAgentDeps(
                    message=message,
                    existing_classes=existing_classes,
                    existing_properties=existing_properties,
                ),
            )
            proposal = ontology_result.output

            candidate_classes, accepted_classes = _merge_classes(existing_classes, proposal.new_classes)
            candidate_properties, accepted_properties = _merge_properties(existing_properties, proposal.new_properties)

            extraction_result = extractor_agent.run_sync(
                "Extract ontology-aligned entities and facts from the current message.",
                deps=ExtractorAgentDeps(
                    message=message,
                    classes=candidate_classes,
                    properties=candidate_properties,
                ),
            )
            extraction = extraction_result.output

            known_entity_ids = repo.load_known_entity_ids()
            known_fact_signatures = repo.load_known_fact_signatures()

            librarian_result = librarian_agent.run_sync(
                "Normalize the extracted data into a persistence payload.",
                deps=LibrarianAgentDeps(
                    message=message,
                    classes=candidate_classes,
                    properties=candidate_properties,
                    extracted_entities=extraction.entities,
                    extracted_facts=extraction.facts,
                    known_entity_ids=known_entity_ids,
                    known_fact_signatures=known_fact_signatures,
                ),
            )
            payload = _normalize_librarian_payload(
                librarian_result.output,
                accepted_classes=accepted_classes,
                accepted_properties=accepted_properties,
            )

            with repo.transaction():
                repo.upsert_message(message)
                counts = repo.apply_librarian_payload(message.message_id, payload)
                repo.record_processing_run(
                    message_id=message.message_id,
                    new_class_count=counts["accepted_classes"],
                    new_property_count=counts["accepted_properties"],
                    entity_count=counts["entities"],
                    canonical_fact_count=counts["canonical_facts"],
                    fact_mention_count=counts["fact_mentions"],
                    summary=payload.summary,
                )

            print(
                f"{message.message_id} classes={counts['accepted_classes']} "
                f"properties={counts['accepted_properties']} "
                f"canonical_facts={counts['canonical_facts']} "
                f"mentions={counts['fact_mentions']}"
            )

        row_counts = {table_name: repo.count_rows(table_name) for table_name in SUMMARY_TABLES}
        return DemoRunSummary(
            db_path=db_path,
            processed_messages=len(SEED_MESSAGES),
            row_counts=row_counts,
        )


def _merge_classes(
    existing_classes: list[OntologyClass],
    proposed_classes: Iterable[OntologyClass],
) -> tuple[list[OntologyClass], list[OntologyClass]]:
    merged_classes = list(existing_classes)
    accepted_classes: list[OntologyClass] = []
    seen_class_ids = {ontology_class.class_id for ontology_class in existing_classes}

    for ontology_class in proposed_classes:
        if ontology_class.class_id in seen_class_ids:
            continue
        seen_class_ids.add(ontology_class.class_id)
        merged_classes.append(ontology_class)
        accepted_classes.append(ontology_class)

    return merged_classes, accepted_classes


def _merge_properties(
    existing_properties: list[OntologyProperty],
    proposed_properties: Iterable[OntologyProperty],
) -> tuple[list[OntologyProperty], list[OntologyProperty]]:
    merged_properties = list(existing_properties)
    accepted_properties: list[OntologyProperty] = []
    seen_property_ids = {ontology_property.property_id for ontology_property in existing_properties}

    for ontology_property in proposed_properties:
        if ontology_property.property_id in seen_property_ids:
            continue
        seen_property_ids.add(ontology_property.property_id)
        merged_properties.append(ontology_property)
        accepted_properties.append(ontology_property)

    return merged_properties, accepted_properties


def _normalize_librarian_payload(
    payload: LibrarianPayload,
    *,
    accepted_classes: list[OntologyClass],
    accepted_properties: list[OntologyProperty],
) -> LibrarianPayload:
    payload_dict = payload.model_dump()
    payload_dict["accepted_classes"] = _dedupe_by_id(
        payload.accepted_classes or accepted_classes,
        key="class_id",
    )
    payload_dict["accepted_properties"] = _dedupe_by_id(
        payload.accepted_properties or accepted_properties,
        key="property_id",
    )
    return LibrarianPayload.model_validate(payload_dict)


def _dedupe_by_id(items: Iterable[object], *, key: str) -> list[object]:
    deduped: list[object] = []
    seen_ids: set[str] = set()

    for item in items:
        item_id = getattr(item, key)
        if item_id in seen_ids:
            continue
        seen_ids.add(item_id)
        deduped.append(item)

    return deduped
