"""Background processing end to end: outbox -> relay -> broker -> handler, over in-memory SQLite."""

import asyncio
from collections.abc import Iterator
from dataclasses import dataclass
from typing import ClassVar

import pytest
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from commons.database import SqlUnitOfWorkFactory, UnitOfWorkFactory
from commons.events import (
    BackgroundWorkers,
    CommitNotifyingUnitOfWorkFactory,
    Event,
    EventEnvelope,
    EventsSettings,
    Outbox,
    OutboxRelay,
    SqlOutbox,
    background_workers_from_settings,
)
from commons.users import SystemUser, User

GROUP = "test-group"


@dataclass
class _Repositories:
    """An app's repository bundle: anything with an ``outbox`` satisfies `HasOutbox`."""

    outbox: Outbox


def _bundle(session: Session, user: User) -> _Repositories:
    return _Repositories(outbox=SqlOutbox(session))


@pytest.fixture
def repositories() -> Iterator[CommitNotifyingUnitOfWorkFactory[_Repositories]]:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    yield CommitNotifyingUnitOfWorkFactory(SqlUnitOfWorkFactory(sessionmaker(bind=engine, class_=Session), _bundle))
    engine.dispose()


class _Requested(Event):
    topic: ClassVar[str] = "test"
    event_type: ClassVar[str] = "requested"

    name: str = "a"


def _settings() -> EventsSettings:
    # Polling slower than the test timeout: delivery must come from the commit signal.
    return EventsSettings(mode="memory", poll_interval_seconds=30)


async def _request(repositories: UnitOfWorkFactory[_Repositories], name: str = "a") -> _Requested:
    """A domain function: stores the event in its unit of work."""
    event = _Requested(name=name)
    with repositories.for_system() as (repos, commit):
        repos.outbox.add_event(event)
        await commit()
    return event


def _unpublished(repositories: UnitOfWorkFactory[_Repositories]) -> list[EventEnvelope]:
    with repositories.for_system() as (repos, _):
        return repos.outbox.list_unpublished(10)


async def _wait_for(condition) -> None:
    async with asyncio.timeout(5):
        while not condition():
            await asyncio.sleep(0.01)


def _workers_with_handler(
    repositories: UnitOfWorkFactory[_Repositories], received: list[_Requested]
) -> BackgroundWorkers:
    workers = background_workers_from_settings(repositories, _settings())

    async def handler(event: _Requested) -> None:
        received.append(event)

    workers.subscribe(group=GROUP, event_type=_Requested, handler=handler)
    return workers


def test_committed_event_is_handled_in_the_background(repositories):
    received: list[_Requested] = []
    workers = _workers_with_handler(repositories, received)

    async def scenario() -> _Requested:
        workers.start()
        try:
            event = await _request(repositories)
            await _wait_for(lambda: bool(received))
            return event
        finally:
            await workers.stop()

    event = asyncio.run(scenario())

    assert received == [event]
    assert _unpublished(repositories) == []


def test_events_committed_while_stopped_are_relayed_at_start(repositories):
    event = asyncio.run(_request(repositories))
    assert len(_unpublished(repositories)) == 1
    received: list[_Requested] = []
    workers = _workers_with_handler(repositories, received)

    async def scenario() -> None:
        workers.start()
        try:
            await _wait_for(lambda: bool(received))
        finally:
            await workers.stop()

    asyncio.run(scenario())

    assert received == [event]


def test_subscribing_after_start_raises(repositories):
    workers = background_workers_from_settings(repositories, _settings())

    async def handler(event: _Requested) -> None: ...

    async def scenario() -> None:
        workers.start()
        try:
            with pytest.raises(RuntimeError, match="before"):
                workers.subscribe(group=GROUP, event_type=_Requested, handler=handler)
        finally:
            await workers.stop()

    asyncio.run(scenario())


def test_starting_twice_raises(repositories):
    workers = background_workers_from_settings(repositories, _settings())

    async def scenario() -> None:
        workers.start()
        try:
            with pytest.raises(RuntimeError, match="already running"):
                workers.start()
        finally:
            await workers.stop()

    asyncio.run(scenario())


def test_maintenance_prunes_and_runs_the_jobs(repositories):
    runs: list[str] = []

    async def job() -> None:
        runs.append("job")

    workers = background_workers_from_settings(repositories, _settings(), maintenance=[job])

    asyncio.run(workers.maintain())

    assert runs == ["job"]


class _FlakyPublisher:
    """Accepts ``accept`` events, then raises."""

    def __init__(self, accept: int) -> None:
        self.accept = accept
        self.published: list[EventEnvelope] = []

    async def publish(self, envelope: EventEnvelope) -> None:
        if len(self.published) >= self.accept:
            raise ConnectionError("broker down")
        self.published.append(envelope)


def test_relay_marks_only_accepted_events_published(repositories):
    for name in ("a", "b", "c"):
        asyncio.run(_request(repositories, name))
    publisher = _FlakyPublisher(accept=2)
    relay = OutboxRelay(repositories, publisher)

    with pytest.raises(ConnectionError):
        asyncio.run(relay.relay_pending())

    (remaining,) = _unpublished(repositories)
    assert remaining.event_id not in {e.event_id for e in publisher.published}

    publisher.accept = 3
    assert asyncio.run(relay.relay_pending()) == 1
    assert _unpublished(repositories) == []
    assert [e.payload["name"] for e in publisher.published] == ["a", "b", "c"]


def test_waking_a_relay_that_is_not_running_does_nothing(repositories):
    OutboxRelay(repositories, _FlakyPublisher(accept=0)).wake()


class _StubbornWork:
    """A worker loop that swallows its first cancellation, like some libraries do."""

    def __init__(self) -> None:
        self.cancellations = 0

    async def run(self) -> None:
        while True:
            try:
                await asyncio.sleep(3600)
            except asyncio.CancelledError:
                self.cancellations += 1
                if self.cancellations > 1:
                    raise


def test_stop_cancels_again_a_task_that_swallowed_its_cancellation(repositories):
    workers = background_workers_from_settings(repositories, _settings())
    stubborn = _StubbornWork()

    async def scenario() -> None:
        workers.start()
        workers._tasks.append(asyncio.create_task(stubborn.run()))
        await asyncio.sleep(0)  # let it enter its loop
        async with asyncio.timeout(5):
            await workers.stop()

    asyncio.run(scenario())

    assert stubborn.cancellations == 2


def test_stop_gives_up_on_a_task_that_never_stops(repositories):
    workers = background_workers_from_settings(repositories, _settings())
    release: asyncio.Event | None = None

    async def never_stops() -> None:
        while True:
            try:
                await asyncio.sleep(3600)
            except asyncio.CancelledError:
                if release is not None and release.is_set():
                    raise

    async def scenario() -> None:
        nonlocal release
        release = asyncio.Event()
        workers.start()
        task = asyncio.create_task(never_stops())
        workers._tasks.append(task)
        await asyncio.sleep(0)  # let it enter its loop
        async with asyncio.timeout(5):
            await workers.stop(timeout=1)
        assert not task.done()
        release.set()
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    asyncio.run(scenario())


@pytest.mark.parametrize("open_unit_of_work", ["for_user", "for_system", "factory"])
def test_every_way_of_opening_a_unit_of_work_notifies(repositories, open_unit_of_work):
    notified: list[str] = []
    repositories.add_commit_listener(lambda: notified.append("commit"))
    unit_of_work = {
        "for_user": lambda: repositories.for_user(SystemUser()),
        "for_system": repositories.for_system,
        "factory": lambda: repositories,
    }[open_unit_of_work]()

    async def write() -> None:
        with unit_of_work as (repos, commit):
            repos.outbox.add_event(_Requested())
            await commit()

    asyncio.run(write())

    assert notified == ["commit"]
    assert len(_unpublished(repositories)) == 1


def test_a_unit_of_work_without_commit_does_not_notify(repositories):
    notified: list[str] = []
    repositories.add_commit_listener(lambda: notified.append("commit"))

    with repositories.for_system() as (repos, _):
        repos.outbox.add_event(_Requested())

    assert notified == []
    assert _unpublished(repositories) == []


def test_a_failing_listener_does_not_fail_the_commit(repositories):
    def failing() -> None:
        raise RuntimeError("listener broken")

    repositories.add_commit_listener(failing)

    asyncio.run(_request(repositories))

    assert len(_unpublished(repositories)) == 1
