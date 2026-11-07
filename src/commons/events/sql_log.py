from datetime import datetime

from sqlalchemy import BigInteger, CursorResult, Engine, UnicodeText, update
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import registry
from sqlmodel import Field, Session, SQLModel, col, select

from commons.database import CODE_LENGTH, NAME_LENGTH, UTCDateTime
from commons.datetime_operators import utc_now

from .event import EventEnvelope


class _Model(SQLModel, registry=registry()):
    """The tables of the log, apart from ``SQLModel.metadata``: apps not using it shouldn't get them."""


class _Topic(_Model, table=True):
    __tablename__ = "event_log_topics"  # type: ignore[assignment]

    topic: str = Field(primary_key=True, max_length=CODE_LENGTH)
    last_sequence: int = Field(default=0, sa_type=BigInteger)


class _Entry(_Model, table=True):
    __tablename__ = "event_log_entries"  # type: ignore[assignment]

    topic: str = Field(primary_key=True, max_length=CODE_LENGTH)
    sequence: int = Field(primary_key=True, sa_type=BigInteger, sa_column_kwargs={"autoincrement": False})
    envelope: str = Field(sa_type=UnicodeText)


class _Offset(_Model, table=True):
    __tablename__ = "event_log_offsets"  # type: ignore[assignment]

    consumer_group: str = Field(primary_key=True, max_length=NAME_LENGTH)
    topic: str = Field(primary_key=True, max_length=CODE_LENGTH)
    position: int = Field(sa_type=BigInteger)


class _DeadLetter(_Model, table=True):
    __tablename__ = "event_log_dead_letters"  # type: ignore[assignment]

    id: int | None = Field(default=None, primary_key=True)
    consumer_group: str = Field(max_length=NAME_LENGTH)
    topic: str = Field(max_length=CODE_LENGTH)
    envelope: str = Field(sa_type=UnicodeText)
    error: str = Field(sa_type=UnicodeText)
    dead_lettered_at: datetime = Field(sa_type=UTCDateTime)


class SqlEventLog:
    """An `EventLog` in a database, durable across restarts, on an engine of its own.

    Each call is a transaction of its own, never part of a domain transaction. The offset of an event is its sequence
    in its topic. An append raises the topic's counter and inserts the event in one transaction: the update holds the
    row until the commit, so a second writer waits, and a topic's events become visible in the order of their
    sequences, without gaps. A consumer can't read past an event that isn't visible yet.

    Args:
        engine: The engine of the log, not the one of the domain's transactions: a slow log must not use up its pool.
    """

    def __init__(self, engine: Engine) -> None:
        self._engine = engine
        try:
            _Model.metadata.create_all(engine)
        except DBAPIError:  # another instance created them at the same time
            _Model.metadata.create_all(engine)

    def append(self, envelope: EventEnvelope) -> None:
        line = envelope.model_dump_json()

        with Session(self._engine) as session:
            if not self._raise_sequence(session, envelope.topic):
                session.rollback()  # the empty update may hold locks, which creating the row would wait for
                self._create_topic(envelope.topic)
                self._raise_sequence(session, envelope.topic)

            sequence = session.exec(select(_Topic.last_sequence).where(_Topic.topic == envelope.topic)).one()
            session.add(_Entry(topic=envelope.topic, sequence=sequence, envelope=line))
            session.commit()

    def read(self, topic: str, offset: int, limit: int) -> list[tuple[EventEnvelope, int]]:
        stmt = (
            select(_Entry)
            .where(_Entry.topic == topic, col(_Entry.sequence) > offset)
            .order_by(col(_Entry.sequence))
            .limit(limit)
        )
        with Session(self._engine) as session:
            return [(EventEnvelope.model_validate_json(e.envelope), e.sequence) for e in session.exec(stmt).all()]

    def committed_offset(self, group: str, topic: str) -> int:
        stmt = select(_Offset.position).where(_Offset.consumer_group == group, _Offset.topic == topic)
        with Session(self._engine) as session:
            return session.exec(stmt).first() or 0

    def commit_offset(self, group: str, topic: str, offset: int) -> None:
        with Session(self._engine) as session:
            if self._update_offset(session, group, topic, offset):
                session.commit()
                return

            session.add(_Offset(consumer_group=group, topic=topic, position=offset))
            try:
                session.commit()
            except IntegrityError:  # another instance inserted it meanwhile
                session.rollback()
                self._update_offset(session, group, topic, offset)
                session.commit()

    def dead_letter(self, group: str, envelope: EventEnvelope, error: str) -> None:
        with Session(self._engine) as session:
            session.add(
                _DeadLetter(
                    consumer_group=group,
                    topic=envelope.topic,
                    envelope=envelope.model_dump_json(),
                    error=error,
                    dead_lettered_at=utc_now(),
                )
            )
            session.commit()

    @staticmethod
    def _raise_sequence(session: Session, topic: str) -> bool:
        """Raise the topic's counter, and hold its row until the commit; ``False`` if the topic has no row yet."""
        result: CursorResult = session.execute(  # type: ignore[assignment]
            update(_Topic).where(col(_Topic.topic) == topic).values(last_sequence=col(_Topic.last_sequence) + 1)
        )
        return result.rowcount > 0

    def _create_topic(self, topic: str) -> None:
        with Session(self._engine) as session:
            session.add(_Topic(topic=topic))
            try:
                session.commit()
            except IntegrityError:  # another writer created it meanwhile
                session.rollback()

    @staticmethod
    def _update_offset(session: Session, group: str, topic: str, offset: int) -> bool:
        result: CursorResult = session.execute(  # type: ignore[assignment]
            update(_Offset)
            .where(col(_Offset.consumer_group) == group, col(_Offset.topic) == topic)
            .values(position=offset)
        )
        return result.rowcount > 0
