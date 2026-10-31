import uuid
from typing import ClassVar

import pytest

from commons.events import Event, EventEnvelope

CONVERSATION_ID = "11111111-1111-1111-1111-111111111111"


class _Requested(Event):
    topic: ClassVar[str] = "test"
    event_type: ClassVar[str] = "requested"

    conversation_id: str

    @property
    def key(self) -> str:
        return self.conversation_id


class _Other(Event):
    topic: ClassVar[str] = "test"
    event_type: ClassVar[str] = "other"


def test_envelope_carries_routing_and_payload():
    event = _Requested(conversation_id=CONVERSATION_ID)

    envelope = event.to_envelope()

    assert (envelope.topic, envelope.event_type, envelope.key) == ("test", "requested", CONVERSATION_ID)
    assert envelope.event_id == event.event_id
    assert envelope.payload["conversation_id"] == CONVERSATION_ID


def test_event_round_trips_through_its_envelope():
    event = _Requested(conversation_id=CONVERSATION_ID)

    assert _Requested.from_envelope(event.to_envelope()) == event


def test_envelope_round_trips_through_its_json():
    event = _Requested(conversation_id=CONVERSATION_ID)
    envelope = event.to_envelope()

    parsed = EventEnvelope.model_validate_json(envelope.model_dump_json())

    assert parsed == envelope
    assert _Requested.from_envelope(parsed) == event


def test_events_get_distinct_time_ordered_ids():
    first, second = _Other(), _Other()

    assert first.event_id != second.event_id
    assert uuid.UUID(first.event_id).version == 7
    assert first.event_id < second.event_id


def test_occurred_at_is_aware_utc():
    assert _Other().occurred_at.utcoffset() is not None


def test_reading_an_envelope_of_another_type_raises():
    with pytest.raises(ValueError, match="not `test/requested`"):
        _Requested.from_envelope(_Other().to_envelope())


def test_reading_an_invalid_payload_raises():
    envelope = _Requested(conversation_id=CONVERSATION_ID).to_envelope().model_copy(update={"payload": {}})

    with pytest.raises(ValueError):
        _Requested.from_envelope(envelope)
