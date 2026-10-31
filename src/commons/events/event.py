from datetime import datetime
from typing import Any, ClassVar, Self
from uuid import uuid7

from pydantic import BaseModel, ConfigDict, Field

from commons.database import ID_LENGTH
from commons.datetime_operators import utc_now


def _new_event_id() -> str:
    return str(uuid7())


class EventEnvelope(BaseModel):
    """The wire format of an `Event`: routing metadata plus the JSON payload.

    The outbox, the relay and the brokers only handle envelopes, so they need no knowledge of the concrete event
    classes. Consumers turn an envelope back into its typed event with `Event.from_envelope`.

    Attributes:
        event_id: The unique id of the event; stable across redeliveries.
        topic: The log the event is appended to.
        key: The partition key: events with the same key keep their order. None means no ordering guarantee.
        event_type: The name of the event on the wire, unique within its topic.
        occurred_at: When the event occurred (UTC).
        payload: The event's fields as JSON.
    """

    model_config = ConfigDict(frozen=True)

    event_id: str
    topic: str
    key: str | None = None
    event_type: str
    occurred_at: datetime
    payload: dict[str, Any]


class Event(BaseModel):
    """Base of all events: an immutable fact, published via the outbox.

    Subclasses set ``topic`` (the log the event is appended to) and ``event_type`` (its name on the wire, unique
    within the topic), and may override `key`: events with the same key are processed in order, events with
    different keys in parallel. Delivery is at least once, so handlers must be idempotent; ``event_id`` is stable
    across redeliveries.

    Attributes:
        event_id: The unique id of the event, a time-ordered UUIDv7 by default.
        occurred_at: When the event occurred (UTC).

    Example:
        ```python
        class RunRequested(Event):
            topic: ClassVar[str] = "runs"
            event_type: ClassVar[str] = "run_requested"

            conversation_id: str
            run_id: str

            @property
            def key(self) -> str:
                return self.conversation_id
        ```
    """

    model_config = ConfigDict(frozen=True)

    topic: ClassVar[str]
    event_type: ClassVar[str]

    event_id: str = Field(default_factory=_new_event_id, min_length=ID_LENGTH, max_length=ID_LENGTH)
    occurred_at: datetime = Field(default_factory=utc_now)

    @property
    def key(self) -> str | None:
        """The partition key: events with the same key keep their order. None means no ordering guarantee."""
        return None

    def to_envelope(self) -> EventEnvelope:
        """Return the event in its wire format."""
        return EventEnvelope(
            event_id=self.event_id,
            topic=self.topic,
            key=self.key,
            event_type=self.event_type,
            occurred_at=self.occurred_at,
            payload=self.model_dump(mode="json"),
        )

    @classmethod
    def from_envelope(cls, envelope: EventEnvelope) -> Self:
        """Return the typed event of an envelope.

        Raises:
            ValueError: If the envelope carries another event type, or its payload does not validate against this
                class (Pydantic's ``ValidationError`` is a ``ValueError``).
        """
        if (envelope.topic, envelope.event_type) != (cls.topic, cls.event_type):
            raise ValueError(
                f"Envelope `{envelope.event_id}` is `{envelope.topic}/{envelope.event_type}`, "
                f"not `{cls.topic}/{cls.event_type}`."
            )

        return cls.model_validate(envelope.payload)
