import asyncio
import logging
from collections import deque
from collections.abc import Awaitable, Callable
from contextlib import suppress
from functools import partial
from dataclasses import dataclass, field
from pydantic import ValidationError
from typing import Any

from .event import Event, EventEnvelope
from .log import EventLog
from .ports import EventHandler


LOG = logging.getLogger(__name__)


@dataclass
class _Subscription:
    """The handlers of one consumer group for one topic, by event type."""

    group: str
    topic: str
    handlers: dict[str, tuple[type[Event], EventHandler[Any]]] = field(default_factory=dict)


class LogBroker:
    """An in-process message broker with Kafka-like semantics on top of an `EventLog`.

    Implements `EventPublisher` and `EventConsumer`. Publishing appends to the topic's log and wakes the consumers of
    that topic. Each (group, topic) subscription reads its topic in order from the group's committed offset and
    processes the events **in order per key**: events with the same key one after the other, events with different
    keys (and events without a key) in parallel, at most ``max_concurrency`` handlers at a time and at most
    ``batch_size`` events in flight.

    The committed offset only moves past events that are all processed, so after a crash every unfinished event is
    delivered again, and some finished ones too: at least once. A failing handler is tried ``max_attempts`` times in
    total, then the event is dead-lettered and skipped; an event that does not validate against its type is
    dead-lettered right away. Either way only its key waits, not the others. Consumers also poll every
    ``poll_interval`` seconds, in case an append bypassed `publish`.

    Single process only: a Kafka or Service Bus adapter would replace this.

    Args:
        log: The storage of the topics, offsets and dead letters.
        poll_interval: Seconds between reads of a topic when the consumer was not woken by a publish.
        batch_size: The maximum number of events read at once, and in flight (running or waiting for their key) per subscription.
        max_concurrency: The maximum number of handlers running at the same time per subscription.
        max_attempts: How often a handler is tried before the event is dead-lettered.
        retry_backoff: Seconds to wait before a retry, multiplied by the number of the failed attempt.
    """

    def __init__(
        self,
        log: EventLog,
        *,
        poll_interval: float = 1.0,
        batch_size: int = 100,
        max_concurrency: int = 10,
        max_attempts: int = 3,
        retry_backoff: float = 1.0,
    ) -> None:
        self._log = log
        self._poll_interval = poll_interval
        self._batch_size = batch_size
        self._max_concurrency = max_concurrency
        self._max_attempts = max_attempts
        self._retry_backoff = retry_backoff
        self._subscriptions: dict[tuple[str, str], _Subscription] = {}
        self._loop: asyncio.AbstractEventLoop | None = None
        self._wake: dict[tuple[str, str], asyncio.Event] = {}

    async def publish(self, envelope: EventEnvelope) -> None:
        self._log.append(envelope)

        loop = self._loop
        for (_, topic), wake in list(self._wake.items()):
            if loop is not None and topic == envelope.topic:
                with suppress(RuntimeError):  # loop closed meanwhile
                    loop.call_soon_threadsafe(wake.set)

    def subscribe[E: Event](self, *, group: str, event_type: type[E], handler: EventHandler[E]) -> None:
        subscription = self._subscriptions.setdefault((group, event_type.topic), _Subscription(group, event_type.topic))
        if event_type.event_type in subscription.handlers:
            raise ValueError(f"Group `{group}` already handles `{event_type.topic}/{event_type.event_type}`.")

        subscription.handlers[event_type.event_type] = (event_type, handler)

    async def run(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._wake = {key: asyncio.Event() for key in self._subscriptions}
        try:
            await asyncio.gather(
                *(self._consume(subscription, self._wake[key]) for key, subscription in self._subscriptions.items())
            )
        finally:
            self._loop = None
            self._wake = {}

    async def _consume(self, subscription: _Subscription, wake: asyncio.Event) -> None:
        consumption = _Consumption(
            self._log,
            subscription,
            self._deliver,
            wake,
            max_in_flight=self._batch_size,
            max_concurrency=self._max_concurrency,
        )
        offset = consumption.committed

        try:
            while True:
                consumption.raise_failure()
                wake.clear()  # before reading, so a publish during the read is not missed
                batch = self._log.read(subscription.topic, offset, self._batch_size)

                if not batch:
                    with suppress(TimeoutError):
                        await asyncio.wait_for(wake.wait(), self._poll_interval)
                    continue

                for envelope, next_offset in batch:
                    await consumption.dispatch(envelope, next_offset)
                    offset = next_offset
        finally:
            await consumption.cancel()

    async def _deliver(self, subscription: _Subscription, envelope: EventEnvelope) -> None:
        """Hand the envelope to its handler; retry, then dead-letter it if that keeps failing."""

        group = subscription.group
        entry = subscription.handlers.get(envelope.event_type)
        if entry is None:
            LOG.debug(f"Group `{group}` skips `{envelope.event_type}` `{envelope.event_id}`")
            return

        event_type, handler = entry
        try:
            event = event_type.from_envelope(envelope)
        except (ValidationError, ValueError) as e:
            LOG.error(f"Group `{group}` cannot read event `{envelope.event_id}`: {e}")
            self._log.dead_letter(group, envelope, f"{type(e).__name__}: {e}")
            return

        for attempt in range(1, self._max_attempts + 1):
            try:
                await handler(event)
                return
            except Exception as e:
                error = f"{type(e).__name__}: {e}"
                if attempt == self._max_attempts:
                    LOG.exception(
                        f"Group `{group}` failed event `{envelope.event_id}` {attempt} times; dead-lettering it"
                    )
                    self._log.dead_letter(group, envelope, error)
                    return

                LOG.warning(f"Group `{group}` failed event `{envelope.event_id}` (attempt {attempt}): {error}")
                await asyncio.sleep(self._retry_backoff * attempt)


@dataclass
class _InFlight:
    """An event dispatched to its key, with the offset to commit once it and all events before it are processed."""

    next_offset: int
    done: bool = False


class _Consumption:
    """The events of one subscription in flight: a chain of tasks per key, and the committed offset.

    Each event becomes a task that waits for the previous event of its key, then for a free handler slot, and then
    delivers the event. When an event is done, the committed offset moves past the longest run of done events from
    the oldest one in flight.
    """

    def __init__(
        self,
        log: EventLog,
        subscription: _Subscription,
        deliver: Callable[[_Subscription, EventEnvelope], Awaitable[None]],
        wake: asyncio.Event,
        *,
        max_in_flight: int,
        max_concurrency: int,
    ) -> None:
        self._log = log
        self._subscription = subscription
        self._deliver = deliver
        self._wake = wake
        self._in_flight_slots = asyncio.Semaphore(max_in_flight)
        self._handler_slots = asyncio.Semaphore(max_concurrency)
        self._in_flight: deque[_InFlight] = deque()
        self._last_of_key: dict[str, asyncio.Task[None]] = {}
        self._tasks: set[asyncio.Task[None]] = set()
        self._failure: BaseException | None = None
        self.committed = log.committed_offset(subscription.group, subscription.topic)

    async def dispatch(self, envelope: EventEnvelope, next_offset: int) -> None:
        """Start processing the event after the previous event of its key; wait while too many are in flight."""

        await self._in_flight_slots.acquire()
        self.raise_failure()

        entry = _InFlight(next_offset)
        self._in_flight.append(entry)
        previous = self._last_of_key.get(envelope.key) if envelope.key is not None else None
        task = asyncio.create_task(self._process(envelope, entry, previous))
        self._tasks.add(task)
        task.add_done_callback(self._finished)

        if envelope.key is not None:
            self._last_of_key[envelope.key] = task
            task.add_done_callback(partial(self._forget, envelope.key))

    def raise_failure(self) -> None:
        """Raise the error of a task that failed unexpectedly, e.g. writing a dead letter, so the consumer restarts."""

        if self._failure is not None:
            raise self._failure

    async def cancel(self) -> None:
        """Cancel the events in flight and wait for them; their offsets are not committed."""

        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)

    async def _process(self, envelope: EventEnvelope, entry: _InFlight, previous: asyncio.Task[None] | None) -> None:
        try:
            if previous is not None:
                await asyncio.wait([previous])  # the outcome is handled by its own callback

            async with self._handler_slots:
                await self._deliver(self._subscription, envelope)

            entry.done = True
            self._commit()
        finally:
            self._in_flight_slots.release()

    def _commit(self) -> None:
        offset = self.committed
        while self._in_flight and self._in_flight[0].done:
            offset = self._in_flight.popleft().next_offset

        if offset != self.committed:
            self._log.commit_offset(self._subscription.group, self._subscription.topic, offset)
            self.committed = offset

    def _finished(self, task: asyncio.Task[None]) -> None:
        self._tasks.discard(task)
        if not task.cancelled() and task.exception() is not None and self._failure is None:
            self._failure = task.exception()
            self._wake.set()  # let the reader raise it now, not at its next poll

    def _forget(self, key: str, task: asyncio.Task[None]) -> None:
        if self._last_of_key.get(key) is task:
            del self._last_of_key[key]
