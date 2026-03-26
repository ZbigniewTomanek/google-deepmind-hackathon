import asyncio
from collections.abc import Callable, Coroutine
from types import SimpleNamespace
from typing import Any, cast

from pydantic_agents_playground.agents import (
    MODEL_NAME,
    MODEL_PROVIDER,
    build_extractor_agent,
    build_librarian_agent,
    build_model,
    build_ontology_agent,
)
from pydantic_agents_playground.schemas import (
    ExtractedEntity,
    ExtractedFact,
    ExtractorAgentDeps,
    LibrarianAgentDeps,
    OntologyAgentDeps,
    OntologyClass,
    OntologyProperty,
    SeedMessage,
)


def render_instruction(agent: Any, deps: Any) -> str:
    instruction = cast(Callable[[Any], Coroutine[Any, Any, str]], agent._instructions[0])
    return asyncio.run(instruction(SimpleNamespace(deps=deps)))


def test_build_model_uses_test_model_when_requested() -> None:
    model = build_model(use_test_model=True)

    assert type(model).__name__ == "TestModel"


def test_build_model_uses_gemini_model_by_default() -> None:
    model = build_model(use_test_model=False)

    assert type(model).__name__ == "GoogleModel"
    assert model.model_name == MODEL_NAME
    assert model.system == MODEL_PROVIDER


def test_ontology_agent_has_expected_configuration_and_instructions() -> None:
    deps = OntologyAgentDeps(
        message=SeedMessage(
            message_id="msg-003",
            title="Inline-six era",
            topic="engines",
            content="BMW made smooth inline-six engines a hallmark of the E36 and E46 generations.",
        ),
        existing_classes=[
            OntologyClass(class_id="car_model", label="Car Model", description="A named car model."),
        ],
        existing_properties=[
            OntologyProperty(
                property_id="has_engine_layout",
                label="has engine layout",
                description="Describes the engine layout used by a model.",
                domain_class_id="car_model",
                value_type="string",
            )
        ],
    )
    agent = build_ontology_agent(use_test_model=True)

    instructions = render_instruction(agent, deps)

    assert agent._output_type.__name__ == "OntologyProposal"
    assert agent._deps_type is OntologyAgentDeps
    assert "generic automotive concepts first" in " ".join(agent._system_prompts)
    assert "Current message:" in instructions
    assert "Current ontology classes:" in instructions
    assert "Current ontology properties:" in instructions
    assert "Prefer extending with properties before creating new classes." in instructions


def test_extractor_agent_instructions_reference_ontology_constraints() -> None:
    deps = ExtractorAgentDeps(
        message=SeedMessage(
            message_id="msg-006",
            title="335i tuning",
            topic="performance",
            content="The turbocharged 335i became known for strong tuning potential.",
        ),
        classes=[
            OntologyClass(class_id="car_model", label="Car Model", description="A named car model."),
        ],
        properties=[
            OntologyProperty(
                property_id="has_reputation",
                label="has reputation",
                description="Captures a notable reputation.",
                domain_class_id="car_model",
                value_type="string",
            )
        ],
    )
    agent = build_extractor_agent(use_test_model=True)

    instructions = render_instruction(agent, deps)

    assert agent._output_type.__name__ == "ExtractionResult"
    assert agent._deps_type is ExtractorAgentDeps
    assert "valid property_id" in " ".join(agent._system_prompts)
    assert "Extract only ontology-aligned entities and facts." in instructions
    assert "If a fact cannot fit the ontology, omit it." in instructions


def test_librarian_agent_instructions_include_normalization_context() -> None:
    deps = LibrarianAgentDeps(
        message=SeedMessage(
            message_id="msg-009",
            title="330e hybrid",
            topic="electrification",
            content="The 330e brought plug-in hybrid technology to the 3 Series range.",
        ),
        classes=[
            OntologyClass(class_id="car_model", label="Car Model", description="A named car model."),
            OntologyClass(class_id="powertrain", label="Powertrain", description="A propulsion setup."),
        ],
        properties=[
            OntologyProperty(
                property_id="has_powertrain",
                label="has powertrain",
                description="Links a model to its powertrain.",
                domain_class_id="car_model",
                value_type="entity",
                range_class_id="powertrain",
            )
        ],
        extracted_entities=[
            ExtractedEntity(
                entity_id="bmw_330e",
                label="BMW 330e",
                class_id="car_model",
                canonical_name="BMW 330e",
            )
        ],
        extracted_facts=[
            ExtractedFact(
                subject_entity_id="bmw_330e",
                property_id="has_powertrain",
                value_type="entity",
                target_entity_id="plug_in_hybrid_powertrain",
                evidence_text="330e brought plug-in hybrid technology",
                confidence=0.88,
            )
        ],
        known_entity_ids=["bmw_330e"],
        known_fact_signatures=['["bmw_330e","has_powertrain","entity","plug_in_hybrid_powertrain"]'],
    )
    agent = build_librarian_agent(use_test_model=True)

    instructions = render_instruction(agent, deps)

    assert agent._output_type.__name__ == "LibrarianPayload"
    assert agent._deps_type is LibrarianAgentDeps
    assert "stable fact signatures" in " ".join(agent._system_prompts)
    assert "Known entity IDs:" in instructions
    assert "Known fact signatures:" in instructions
    assert "Always fill source_message_id on fact mentions." in instructions
