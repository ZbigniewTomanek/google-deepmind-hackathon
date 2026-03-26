from collections.abc import Iterable

from loguru import logger

from pydantic_agents_playground.agents import (
    build_extractor_agent,
    build_librarian_agent,
    build_ontology_agent,
    run_stage,
)
from pydantic_agents_playground.database import SQLiteRepository
from pydantic_agents_playground.logging import configure_logging
from pydantic_agents_playground.messages import SEED_MESSAGES
from pydantic_agents_playground.schemas import (
    DemoRunSummary,
    ExtractorAgentDeps,
    LibrarianAgentDeps,
    LibrarianPayload,
    OntologyAgentDeps,
    OntologyClass,
    OntologyProperty,
    PersistedFact,
    PersistedFactMention,
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
    message_limit: int | None = 5,
) -> DemoRunSummary:
    configure_logging()
    messages = SEED_MESSAGES if message_limit is None else SEED_MESSAGES[:message_limit]
    logger.info(
        "Starting demo run db_path={} use_test_model={} reset_db={} message_count={}",
        db_path,
        use_test_model,
        reset_db,
        len(messages),
    )
    with SQLiteRepository(db_path) as repo:
        repo.create_schema()
        if reset_db:
            repo.reset_database()

        ontology_agent = build_ontology_agent(use_test_model=use_test_model)
        extractor_agent = build_extractor_agent(use_test_model=use_test_model)
        librarian_agent = build_librarian_agent(use_test_model=use_test_model)

        for index, message in enumerate(messages, start=1):
            logger.info(
                "Processing message {}/{} message_id={} topic={} title={}",
                index,
                len(messages),
                message.message_id,
                message.topic,
                message.title,
            )
            logger.debug("Input message for {}: {}", message.message_id, message.model_dump())
            existing_classes, existing_properties = repo.load_ontology()

            ontology_result = run_stage(
                ontology_agent,
                "Review the current message and propose conservative ontology additions.",
                OntologyAgentDeps(
                    message=message,
                    existing_classes=existing_classes,
                    existing_properties=existing_properties,
                ),
                stage_name=f"ontology:{message.message_id}",
            )
            proposal = ontology_result.output
            logger.debug("Ontology proposal for {}: {}", message.message_id, proposal.model_dump())

            candidate_classes, accepted_classes = _merge_classes(existing_classes, proposal.new_classes)
            candidate_properties, accepted_properties = _merge_properties(existing_properties, proposal.new_properties)
            logger.info(
                "Ontology stage for {} proposed classes={} properties={} accepted_classes={} accepted_properties={}",
                message.message_id,
                len(proposal.new_classes),
                len(proposal.new_properties),
                len(accepted_classes),
                len(accepted_properties),
            )

            extraction_result = run_stage(
                extractor_agent,
                "Extract ontology-aligned entities and facts from the current message.",
                ExtractorAgentDeps(
                    message=message,
                    classes=candidate_classes,
                    properties=candidate_properties,
                ),
                stage_name=f"extractor:{message.message_id}",
            )
            extraction = extraction_result.output
            logger.debug("Extraction result for {}: {}", message.message_id, extraction.model_dump())
            logger.info(
                "Extractor stage for {} produced entities={} facts={}",
                message.message_id,
                len(extraction.entities),
                len(extraction.facts),
            )

            known_entity_ids = repo.load_known_entity_ids()
            known_fact_signatures = repo.load_known_fact_signatures()

            librarian_result = run_stage(
                librarian_agent,
                "Normalize the extracted data into a persistence payload.",
                LibrarianAgentDeps(
                    message=message,
                    classes=candidate_classes,
                    properties=candidate_properties,
                    extracted_entities=extraction.entities,
                    extracted_facts=extraction.facts,
                    known_entity_ids=known_entity_ids,
                    known_fact_signatures=known_fact_signatures,
                ),
                stage_name=f"librarian:{message.message_id}",
            )
            payload = _normalize_librarian_payload(
                librarian_result.output,
                accepted_classes=accepted_classes,
                accepted_properties=accepted_properties,
            )
            logger.debug("Normalized librarian payload for {}: {}", message.message_id, payload.model_dump())
            logger.info(
                "Librarian stage for {} prepared accepted_classes={} accepted_properties={} "
                "entities={} canonical_facts={} mentions={}",
                message.message_id,
                len(payload.accepted_classes),
                len(payload.accepted_properties),
                len(payload.entities_to_upsert),
                len(payload.canonical_facts_to_upsert),
                len(payload.fact_mentions_to_insert),
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
            logger.info("Finished message {} with persisted counts={}", message.message_id, counts)

        row_counts = {table_name: repo.count_rows(table_name) for table_name in SUMMARY_TABLES}
        logger.info("Demo run complete with row_counts={}", row_counts)
        return DemoRunSummary(
            db_path=db_path,
            processed_messages=len(messages),
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
    normalized_payload = LibrarianPayload.model_validate(payload_dict)
    repaired_payload = _ensure_canonical_facts_cover_mentions(normalized_payload)
    if len(repaired_payload.canonical_facts_to_upsert) > len(normalized_payload.canonical_facts_to_upsert):
        logger.warning(
            "Derived {} missing canonical facts from fact mentions during payload normalization",
            len(repaired_payload.canonical_facts_to_upsert) - len(normalized_payload.canonical_facts_to_upsert),
        )
    return repaired_payload


def _ensure_canonical_facts_cover_mentions(payload: LibrarianPayload) -> LibrarianPayload:
    canonical_facts_by_signature: dict[tuple[object, ...], PersistedFact] = {
        _fact_identity(
            fact.subject_entity_id,
            fact.property_id,
            fact.value_type,
            fact.string_value,
            fact.number_value,
            fact.boolean_value,
            fact.date_value,
            fact.target_entity_id,
        ): fact
        for fact in payload.canonical_facts_to_upsert
    }

    for mention in payload.fact_mentions_to_insert:
        signature = _fact_identity(
            mention.subject_entity_id,
            mention.property_id,
            mention.value_type,
            mention.string_value,
            mention.number_value,
            mention.boolean_value,
            mention.date_value,
            mention.target_entity_id,
        )
        canonical_facts_by_signature.setdefault(signature, _canonical_fact_from_mention(mention))

    payload_dict = payload.model_dump()
    payload_dict["canonical_facts_to_upsert"] = list(canonical_facts_by_signature.values())
    return LibrarianPayload.model_validate(payload_dict)


def _canonical_fact_from_mention(mention: PersistedFactMention) -> PersistedFact:
    return PersistedFact(
        subject_entity_id=mention.subject_entity_id,
        property_id=mention.property_id,
        value_type=mention.value_type,
        string_value=mention.string_value,
        number_value=mention.number_value,
        boolean_value=mention.boolean_value,
        date_value=mention.date_value,
        target_entity_id=mention.target_entity_id,
    )


def _fact_identity(
    subject_entity_id: str,
    property_id: str,
    value_type: str,
    string_value: str | None,
    number_value: float | None,
    boolean_value: bool | None,
    date_value: str | None,
    target_entity_id: str | None,
) -> tuple[object, ...]:
    normalized_number = None if number_value is None else float(f"{number_value:.15g}")
    normalized_string = None if string_value is None else string_value.strip()
    normalized_date = None if date_value is None else date_value.strip()
    return (
        subject_entity_id,
        property_id,
        value_type,
        normalized_string,
        normalized_number,
        boolean_value,
        normalized_date,
        target_entity_id,
    )


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
