import pytest
from pydantic import ValidationError

from neocortex.ingestion.models import EventsIngestionRequest, IngestionResult, TextIngestionRequest


def test_text_request_minimal():
    req = TextIngestionRequest(text="hello")
    assert req.text == "hello"
    assert req.metadata == {}


def test_text_request_with_metadata():
    req = TextIngestionRequest(text="hello", metadata={"source": "test"})
    assert req.metadata == {"source": "test"}


def test_text_request_requires_text():
    with pytest.raises(ValidationError):
        TextIngestionRequest()  # ty: ignore[missing-argument]


def test_events_request_minimal():
    req = EventsIngestionRequest(events=[{"type": "click"}])
    assert len(req.events) == 1
    assert req.metadata == {}


def test_events_request_with_metadata():
    req = EventsIngestionRequest(events=[{"a": 1}], metadata={"batch": "1"})
    assert req.metadata == {"batch": "1"}


def test_events_request_requires_events():
    with pytest.raises(ValidationError):
        EventsIngestionRequest()  # ty: ignore[missing-argument]


def test_ingestion_result_stored():
    r = IngestionResult(status="stored", episodes_created=1, message="ok")
    assert r.status == "stored"
    assert r.episodes_created == 1


def test_ingestion_result_partial():
    r = IngestionResult(status="partial", episodes_created=2, message="partial")
    assert r.status == "partial"


def test_ingestion_result_failed():
    r = IngestionResult(status="failed", episodes_created=0, message="bad")
    assert r.status == "failed"


def test_ingestion_result_invalid_status():
    with pytest.raises(ValidationError):
        IngestionResult(status="unknown", episodes_created=0, message="nope")  # ty: ignore[invalid-argument-type]
