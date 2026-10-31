"""`LogBroker` over the in-memory and the file event log: typed delivery, offsets, retries and dead letters."""

import asyncio
import json
from collections.abc import Callable
from contextlib import suppress
from pathlib import Path
from typing import ClassVar

import pytest

from commons.events import Event
from commons.events import EventLog, FileEventLog, InMemoryEventLog, LogBroker


GROUP = "test-group"
CONVERSATION_ID = "11111111-1111-1111-1111-111111111111"


class _Requested(Event):
    topic: ClassVar[str] = "test"
    event_type: ClassVar[str] = "requested"

    name: str = "a"
    partition: str | None = None

    @property
    def key(self) -> str | None:
        return self.partition


class _Archived(Event):
    """A second event type on the same topic."""

    topic: ClassVar[str] = "test"
    event_type: ClassVar[str] = "archived"

    conversation_id: str = CONVERSATION_ID


@pytest.fixture(params=["memory", "file"])
def log(request, tmp_path: Path) -> EventLog:
    return InMemoryEventLog() if request.param == "memory" else FileEventLog(tmp_path)


def _broker(log: EventLog, **kw) -> LogBroker:
    return LogBroker(log, poll_interval=0.05, retry_backoff=0, **kw)


async def _consume_until(broker: LogBroker, done: Callable[[], bool]) -> None:
    task = asyncio.create_task(broker.run())
    try:
        async with asyncio.timeout(2):
            while not done():
                await asyncio.sleep(0.01)
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task


def test_handlers_receive_typed_events_of_their_type(log: EventLog):
    broker = _broker(log)
    requested: list[_Requested] = []
    archived: list[_Archived] = []

    async def on_requested(event: _Requested) -> None:
        requested.append(event)

    async def on_archived(event: _Archived) -> None:
        archived.append(event)

    broker.subscribe(group=GROUP, event_type=_Requested, handler=on_requested)
    broker.subscribe(group=GROUP, event_type=_Archived, handler=on_archived)
    first, second = _Requested(), _Archived()

    async def scenario() -> None:
        await broker.publish(first.to_envelope())
        await broker.publish(second.to_envelope())
        await _consume_until(broker, lambda: bool(requested and archived))

    asyncio.run(scenario())

    assert requested == [first]
    assert archived == [second]
    assert log.committed_offset(GROUP, _Requested.topic) > 0


def test_events_published_while_consuming_are_delivered(log: EventLog):
    broker = _broker(log)
    received: list[_Requested] = []

    async def handler(event: _Requested) -> None:
        received.append(event)

    broker.subscribe(group=GROUP, event_type=_Requested, handler=handler)
    event = _Requested()

    async def scenario() -> None:
        async def publish_later() -> None:
            await asyncio.sleep(0.1)
            await broker.publish(event.to_envelope())

        publishing = asyncio.create_task(publish_later())
        await _consume_until(broker, lambda: bool(received))
        await publishing

    asyncio.run(scenario())

    assert received == [event]


def test_consumer_continues_from_committed_offset(log: EventLog):
    received: list[_Requested] = []

    async def handler(event: _Requested) -> None:
        received.append(event)

    first, second = _Requested(), _Requested()

    async def consume(event: _Requested) -> None:
        broker = _broker(log)  # a fresh broker, as after a restart
        broker.subscribe(group=GROUP, event_type=_Requested, handler=handler)
        await broker.publish(event.to_envelope())
        await _consume_until(broker, lambda: received[-1:] == [event])

    asyncio.run(consume(first))
    asyncio.run(consume(second))

    assert received == [first, second]


def test_groups_consume_independently(log: EventLog):
    broker = _broker(log)
    received: dict[str, list[_Requested]] = {"a": [], "b": []}
    for group, events in received.items():

        async def handler(event: _Requested, events=events) -> None:
            events.append(event)

        broker.subscribe(group=group, event_type=_Requested, handler=handler)
    event = _Requested()

    async def scenario() -> None:
        await broker.publish(event.to_envelope())
        await _consume_until(broker, lambda: all(received.values()))

    asyncio.run(scenario())

    assert received == {"a": [event], "b": [event]}


def test_failing_event_is_retried_then_dead_lettered():
    log = InMemoryEventLog()
    broker = _broker(log, max_attempts=3)
    attempts: list[str] = []
    handled: list[str] = []

    async def handler(event: _Requested) -> None:
        attempts.append(event.name)
        if event.name == "failing":
            raise RuntimeError("boom")
        handled.append(event.name)

    broker.subscribe(group=GROUP, event_type=_Requested, handler=handler)
    failing, following = _Requested(name="failing", partition="p"), _Requested(name="following", partition="p")

    async def scenario() -> None:
        await broker.publish(failing.to_envelope())
        await broker.publish(following.to_envelope())
        await _consume_until(broker, lambda: bool(handled))

    asyncio.run(scenario())

    assert attempts == ["failing"] * 3 + ["following"]
    assert [letter.envelope.event_id for letter in log.dead_letters] == [failing.event_id]
    assert log.dead_letters[0].error == "RuntimeError: boom"


def test_invalid_event_is_dead_lettered_without_calling_the_handler():
    log = InMemoryEventLog()
    broker = _broker(log)
    handled: list[_Requested] = []

    async def handler(event: _Requested) -> None:
        handled.append(event)

    broker.subscribe(group=GROUP, event_type=_Requested, handler=handler)
    invalid = _Requested().to_envelope().model_copy(update={"payload": {"event_id": "x"}})

    async def scenario() -> None:
        await broker.publish(invalid)
        await _consume_until(broker, lambda: bool(log.dead_letters))

    asyncio.run(scenario())

    assert handled == []
    assert log.dead_letters[0].error.startswith("ValidationError")


def test_events_without_handler_are_skipped(log: EventLog):
    broker = _broker(log)
    received: list[_Requested] = []

    async def handler(event: _Requested) -> None:
        received.append(event)

    broker.subscribe(group=GROUP, event_type=_Requested, handler=handler)
    event = _Requested()

    async def scenario() -> None:
        await broker.publish(_Archived().to_envelope())
        await broker.publish(event.to_envelope())
        await _consume_until(broker, lambda: bool(received))

    asyncio.run(scenario())

    assert received == [event]


def test_subscribing_a_type_twice_in_a_group_raises():
    broker = _broker(InMemoryEventLog())

    async def handler(event: _Requested) -> None: ...

    broker.subscribe(group=GROUP, event_type=_Requested, handler=handler)

    with pytest.raises(ValueError, match="already handles"):
        broker.subscribe(group=GROUP, event_type=_Requested, handler=handler)


def test_file_log_ignores_an_unfinished_line(tmp_path: Path):
    log = FileEventLog(tmp_path)
    event = _Requested()
    log.append(event.to_envelope())
    with (tmp_path / f"{event.topic}.jsonl").open("a") as file:
        file.write('{"event_id": "cut short')

    read = log.read(event.topic, 0, 10)

    assert [envelope for envelope, _ in read] == [event.to_envelope()]
    assert log.read(event.topic, read[-1][1], 10) == []


def test_file_log_keeps_dead_letters_and_offsets_on_disk(tmp_path: Path):
    log = FileEventLog(tmp_path)
    envelope = _Requested().to_envelope()

    log.commit_offset(GROUP, envelope.topic, 42)
    log.dead_letter(GROUP, envelope, "RuntimeError: boom")

    assert FileEventLog(tmp_path).committed_offset(GROUP, envelope.topic) == 42
    path = tmp_path / "_dead_letters" / GROUP / f"{envelope.topic}.jsonl"
    entry = json.loads(path.read_text())
    assert entry["error"] == "RuntimeError: boom"
    assert entry["envelope"]["event_id"] == envelope.event_id


def test_file_log_rejects_unsafe_names(tmp_path: Path):
    with pytest.raises(ValueError, match="not a valid"):
        FileEventLog(tmp_path).committed_offset("../escape", "topic")


# Per-key concurrency


def _concurrency_probe(broker: LogBroker, release: asyncio.Event | None = None):
    """Subscribe a handler that records start and end of every event and how many ran at once."""

    log: list[tuple[str, str]] = []
    running = {"now": 0, "max": 0}

    async def handler(event: _Requested) -> None:
        running["now"] += 1
        running["max"] = max(running["max"], running["now"])
        log.append(("start", event.name))
        if release is not None and event.name.startswith("slow"):
            await release.wait()
        else:
            await asyncio.sleep(0.02)
        log.append(("end", event.name))
        running["now"] -= 1

    broker.subscribe(group=GROUP, event_type=_Requested, handler=handler)
    return log, running


def _ended(log: list[tuple[str, str]]) -> set[str]:
    return {name for kind, name in log if kind == "end"}


def test_events_of_one_key_are_processed_one_after_the_other(log: EventLog):
    broker = _broker(log)
    events_log, running = _concurrency_probe(broker)
    names = ["a1", "a2", "a3"]

    async def scenario() -> None:
        for name in names:
            await broker.publish(_Requested(name=name, partition="a").to_envelope())
        await _consume_until(broker, lambda: _ended(events_log) == set(names))

    asyncio.run(scenario())

    assert events_log == [(kind, name) for name in names for kind in ("start", "end")]
    assert running["max"] == 1


def test_events_of_different_keys_are_processed_in_parallel(log: EventLog):
    broker = _broker(log)
    events_log, running = _concurrency_probe(broker)
    names = ["a", "b", "c"]

    async def scenario() -> None:
        for name in names:
            await broker.publish(_Requested(name=name, partition=name).to_envelope())
        await _consume_until(broker, lambda: _ended(events_log) == set(names))

    asyncio.run(scenario())

    assert [kind for kind, _ in events_log[:3]] == ["start"] * 3
    assert running["max"] == 3


def test_events_without_key_are_processed_in_parallel(log: EventLog):
    broker = _broker(log)
    events_log, running = _concurrency_probe(broker)

    async def scenario() -> None:
        for name in ("x", "y"):
            await broker.publish(_Requested(name=name).to_envelope())
        await _consume_until(broker, lambda: _ended(events_log) == {"x", "y"})

    asyncio.run(scenario())

    assert running["max"] == 2


def test_at_most_max_concurrency_handlers_run_at_once(log: EventLog):
    broker = _broker(log, max_concurrency=2)
    events_log, running = _concurrency_probe(broker)
    names = [f"k{i}" for i in range(5)]

    async def scenario() -> None:
        for name in names:
            await broker.publish(_Requested(name=name, partition=name).to_envelope())
        await _consume_until(broker, lambda: _ended(events_log) == set(names))

    asyncio.run(scenario())

    assert running["max"] == 2


def test_offset_only_moves_past_events_that_are_all_processed():
    log = InMemoryEventLog()
    broker = _broker(log)
    release = asyncio.Event()
    events_log, _ = _concurrency_probe(broker, release)

    async def scenario() -> tuple[int, int]:
        await broker.publish(_Requested(name="slow", partition="a").to_envelope())
        await broker.publish(_Requested(name="fast", partition="b").to_envelope())
        task = asyncio.create_task(broker.run())
        try:
            async with asyncio.timeout(2):
                while "fast" not in _ended(events_log):
                    await asyncio.sleep(0.01)
            while_slow_runs = log.committed_offset(GROUP, _Requested.topic)

            release.set()
            async with asyncio.timeout(2):
                while log.committed_offset(GROUP, _Requested.topic) != 2:
                    await asyncio.sleep(0.01)
            return while_slow_runs, log.committed_offset(GROUP, _Requested.topic)
        finally:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

    while_slow_runs, after = asyncio.run(scenario())

    assert while_slow_runs == 0  # "fast" is done, but "slow" before it is not
    assert after == 2


def test_after_a_restart_unfinished_events_are_delivered_again():
    log = InMemoryEventLog()
    release = asyncio.Event()
    first = _broker(log)
    first_log, _ = _concurrency_probe(first, release)

    async def crash_while_slow_runs() -> None:
        await first.publish(_Requested(name="slow", partition="a").to_envelope())
        await first.publish(_Requested(name="fast", partition="b").to_envelope())
        await _consume_until(first, lambda: "fast" in _ended(first_log))

    asyncio.run(crash_while_slow_runs())

    second = _broker(log)
    second_log, _ = _concurrency_probe(second)
    asyncio.run(_consume_until(second, lambda: _ended(second_log) == {"slow", "fast"}))

    assert _ended(second_log) == {"slow", "fast"}  # "fast" again: at least once
    assert log.committed_offset(GROUP, _Requested.topic) == 2


def test_an_unexpected_failure_stops_the_consumer_so_it_is_restarted():
    class _BrokenDeadLetters(InMemoryEventLog):
        def dead_letter(self, group, envelope, error) -> None:
            raise OSError("disk full")

    log = _BrokenDeadLetters()
    broker = _broker(log, max_attempts=1)

    async def handler(event: _Requested) -> None:
        raise RuntimeError("boom")

    broker.subscribe(group=GROUP, event_type=_Requested, handler=handler)

    async def scenario() -> None:
        await broker.publish(_Requested().to_envelope())
        async with asyncio.timeout(2):
            await broker.run()

    with pytest.raises(OSError, match="disk full"):
        asyncio.run(scenario())

    assert log.committed_offset(GROUP, _Requested.topic) == 0
