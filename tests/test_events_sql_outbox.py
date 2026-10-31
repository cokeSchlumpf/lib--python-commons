"""`SqlOutbox` over in-memory SQLite."""

from collections.abc import Callable, Iterator
from datetime import timedelta
from typing import ClassVar

import pytest
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from commons.datetime_operators import utc_now
from commons.events import Event, SqlOutbox


class _Requested(Event):
    topic: ClassVar[str] = "test"
    event_type: ClassVar[str] = "requested"

    name: str = "a"


@pytest.fixture
def session_factory() -> Iterator[sessionmaker]:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    yield sessionmaker(bind=engine, class_=Session)
    engine.dispose()


def _write(factory: sessionmaker, do: Callable[[SqlOutbox], object]):
    session = factory()
    try:
        result = do(SqlOutbox(session))
        session.commit()
        return result
    finally:
        session.close()


def _read(factory: sessionmaker) -> SqlOutbox:
    return SqlOutbox(factory())


def test_added_events_are_unpublished_in_order(session_factory):
    first, second = _Requested(), _Requested()
    _write(session_factory, lambda outbox: outbox.add_event(first))
    _write(session_factory, lambda outbox: outbox.add_event(second))

    envelopes = _read(session_factory).list_unpublished(10)

    assert [envelope.event_id for envelope in envelopes] == [first.event_id, second.event_id]
    assert envelopes[0] == first.to_envelope()
    assert _Requested.from_envelope(envelopes[0]) == first


def test_event_added_without_commit_is_not_stored(session_factory):
    session = session_factory()
    SqlOutbox(session).add_event(_Requested())
    session.rollback()
    session.close()

    assert _read(session_factory).list_unpublished(10) == []


def test_list_unpublished_respects_limit(session_factory):
    for _ in range(3):
        _write(session_factory, lambda outbox: outbox.add_event(_Requested()))

    assert len(_read(session_factory).list_unpublished(2)) == 2


def test_marking_unknown_or_no_ids_is_ignored(session_factory):
    event = _Requested()
    _write(session_factory, lambda outbox: outbox.add_event(event))

    _write(session_factory, lambda outbox: outbox.mark_published([], utc_now()))
    _write(session_factory, lambda outbox: outbox.mark_published(["unknown"], utc_now()))

    assert [envelope.event_id for envelope in _read(session_factory).list_unpublished(10)] == [event.event_id]


def test_published_events_are_not_listed_and_pruned(session_factory):
    old, recent, unpublished = _Requested(), _Requested(), _Requested()
    for event in (old, recent, unpublished):
        _write(session_factory, lambda outbox, event=event: outbox.add_event(event))
    now = utc_now()
    _write(session_factory, lambda outbox: outbox.mark_published([old.event_id], now - timedelta(days=8)))
    _write(session_factory, lambda outbox: outbox.mark_published([recent.event_id], now))

    listed = _read(session_factory).list_unpublished(10)
    deleted = _write(session_factory, lambda outbox: outbox.delete_published_before(now - timedelta(days=7)))

    assert [envelope.event_id for envelope in listed] == [unpublished.event_id]
    assert deleted == 1
    assert _write(session_factory, lambda outbox: outbox.delete_published_before(now)) == 0
