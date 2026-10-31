"""Events with a transactional outbox: stored with the change that caused them, delivered at least once.

- **Events** (`Event`, `EventEnvelope`): immutable facts with a topic, a type and an optional ordering key.
- **Ports** (`Outbox`, `HasOutbox`, `EventPublisher`, `EventSubscriber`, `EventConsumer`, `EventHandler`).
- **SQL outbox** (`SqlOutbox`, `SqlOutboxEvent`): the table ``outbox_events``, written in the caller's unit of work.
"""

from .event import Event, EventEnvelope
from .ports import EventConsumer, EventHandler, EventPublisher, EventSubscriber, HasOutbox, Outbox
from .sql import SqlOutbox, SqlOutboxEvent

__all__ = [
    "Event",
    "EventConsumer",
    "EventEnvelope",
    "EventHandler",
    "EventPublisher",
    "EventSubscriber",
    "HasOutbox",
    "Outbox",
    "SqlOutbox",
    "SqlOutboxEvent",
]
