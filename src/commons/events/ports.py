from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Protocol

from .event import Event, EventEnvelope


class Outbox(Protocol):
    """The transactional outbox: events stored together with the change that caused them.

    An outbox shares the unit of work of the other repositories, so an added event is stored if and only if the
    change is committed. The outbox relay later publishes the stored events and marks them published.
    """

    def add_event(self, event: Event) -> None:
        """Store the event for publishing once the unit of work commits."""
        ...

    def list_unpublished(self, limit: int) -> list[EventEnvelope]:
        """Return at most ``limit`` unpublished events, in the order they were added."""
        ...

    def mark_published(self, event_ids: list[str], published_at: datetime) -> None:
        """Mark the events with the given ids published; unknown ids are ignored."""
        ...

    def delete_published_before(self, before: datetime) -> int:
        """Delete the events published before ``before``; return how many were deleted."""
        ...


class HasOutbox(Protocol):
    """A repository bundle of a unit of work that contains the outbox, e.g. an app's ``Repositories`` dataclass.

    The relay needs nothing else of the bundle, so any app's or library's bundle with an ``outbox`` field works.
    """

    @property
    def outbox(self) -> Outbox:
        """The outbox, sharing the unit of work's transaction."""
        ...


class EventPublisher(Protocol):
    """Appends events to the message broker, e.g. a Kafka producer.

    Only the outbox relay publishes; domain functions add events to the `Outbox` instead.
    """

    async def publish(self, envelope: EventEnvelope) -> None:
        """Durably append the envelope to its topic; raise if it was not accepted."""
        ...


type EventHandler[E: Event] = Callable[[E], Awaitable[object]]
"""Processes one typed event; raising makes the consumer retry the event."""


class EventSubscriber(Protocol):
    """Registers the handlers of events, e.g. an `EventConsumer` or the background workers."""

    def subscribe[E: Event](self, *, group: str, event_type: type[E], handler: EventHandler[E]) -> None:
        """Let ``group`` process the events of ``event_type`` with ``handler``.

        Raises:
            ValueError: If ``group`` already has a handler for ``event_type``.
        """
        ...


class EventConsumer(EventSubscriber, Protocol):
    """Consumes events from the message broker, e.g. Kafka consumer groups.

    Each consumer ``group`` reads every topic it subscribed to from its own committed offset and processes the events
    **in order per key** (`Event.key`): events with the same key one after the other, events with different keys,
    or without a key, possibly in parallel. Handlers must not rely on an order across keys. An offset is committed
    only once the event and all events before it were processed: delivery is at least once. An event whose handler
    keeps failing is dead-lettered, so it cannot block its key. Events of types the group has no handler for are
    skipped.
    """

    async def run(self) -> None:
        """Consume all subscriptions until cancelled."""
        ...
