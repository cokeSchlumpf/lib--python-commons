from datetime import datetime, timezone
from typing import Any

from sqlalchemy import JSON, CursorResult, delete, update
from sqlmodel import Field, Session, SQLModel, col, select

from commons.database import CODE_LENGTH, ID_LENGTH, NAME_LENGTH, UTCDateTime

from .event import Event, EventEnvelope


def _utc(value: datetime) -> datetime:
    """Return the datetime as aware UTC: ``UTCDateTime`` reads back naive UTC, events use aware ones."""
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


class SqlOutboxEvent(SQLModel, table=True):
    """The persistence row of one outbox event (``outbox_events``).

    Not historized: the outbox is plumbing, not domain state. ``sequence`` (an autoincrement key) keeps the order the
    events were added in; ``published_at`` is ``NULL`` until the relay published the event. One table per
    application: the app and the libraries it uses add their events to it, on their own topics.
    """

    __tablename__ = "outbox_events"  # type: ignore[assignment]

    sequence: int | None = Field(default=None, primary_key=True)
    event_id: str = Field(unique=True, max_length=ID_LENGTH)
    topic: str = Field(max_length=CODE_LENGTH)
    key: str | None = Field(default=None, max_length=NAME_LENGTH)
    event_type: str = Field(max_length=CODE_LENGTH)
    occurred_at: datetime = Field(sa_type=UTCDateTime)
    payload: dict[str, Any] = Field(sa_type=JSON)
    published_at: datetime | None = Field(default=None, sa_type=UTCDateTime, index=True)

    @staticmethod
    def from_envelope(envelope: EventEnvelope) -> "SqlOutboxEvent":
        """Return the row of an envelope."""
        return SqlOutboxEvent(
            event_id=envelope.event_id,
            topic=envelope.topic,
            key=envelope.key,
            event_type=envelope.event_type,
            occurred_at=envelope.occurred_at,
            payload=envelope.payload,
        )

    def to_envelope(self) -> EventEnvelope:
        """Return the envelope of the row."""
        return EventEnvelope(
            event_id=self.event_id,
            topic=self.topic,
            key=self.key,
            event_type=self.event_type,
            occurred_at=_utc(self.occurred_at),
            payload=self.payload,
        )


class SqlOutbox:
    """The SQL adapter of the `Outbox` port, on the table ``outbox_events``.

    The outbox never commits; the caller (the unit of work) owns the transaction, so an added event is stored
    together with the change that caused it.

    Args:
        session: The session of the unit of work.
    """

    def __init__(self, session: Session) -> None:
        self.session = session

    def add_event(self, event: Event) -> None:
        self.session.add(SqlOutboxEvent.from_envelope(event.to_envelope()))

    def list_unpublished(self, limit: int) -> list[EventEnvelope]:
        stmt = (
            select(SqlOutboxEvent)
            .where(col(SqlOutboxEvent.published_at).is_(None))
            .order_by(col(SqlOutboxEvent.sequence))
            .limit(limit)
        )
        return [row.to_envelope() for row in self.session.exec(stmt).all()]

    def mark_published(self, event_ids: list[str], published_at: datetime) -> None:
        if not event_ids:
            return

        self.session.execute(
            update(SqlOutboxEvent).where(col(SqlOutboxEvent.event_id).in_(event_ids)).values(published_at=published_at)
        )

    def delete_published_before(self, before: datetime) -> int:
        result: CursorResult = self.session.execute(  # type: ignore[assignment]
            delete(SqlOutboxEvent).where(col(SqlOutboxEvent.published_at) < before)
        )
        return result.rowcount
