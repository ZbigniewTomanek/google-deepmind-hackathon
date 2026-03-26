from pydantic_agents_playground.schemas import OntologyProposal, SeedMessage


def test_schema_models_can_be_instantiated() -> None:
    message = SeedMessage(
        message_id="msg-001",
        title="BMW 320d launch",
        topic="product",
        content="The BMW 320d Touring debuted with updated mild-hybrid tech.",
    )

    proposal = OntologyProposal(rationale="Seed schema smoke test.")

    assert message.message_id == "msg-001"
    assert proposal.new_classes == []
    assert proposal.new_properties == []
