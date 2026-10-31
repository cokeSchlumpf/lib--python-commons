"""Events with a transactional outbox: stored with the change that caused them, delivered at least once.

- **Events** (`Event`, `EventEnvelope`): immutable facts with a topic, a type and an optional ordering key.
- **Ports** (`Outbox`, `HasOutbox`, `EventPublisher`, `EventSubscriber`, `EventConsumer`, `EventHandler`).
- **Broker** (`LogBroker` on an `EventLog`: `InMemoryEventLog`, `FileEventLog`): in-process, Kafka-like, single instance.
- **SQL outbox** (`SqlOutbox`, `SqlOutboxEvent`): the table ``outbox_events``, written in the caller's unit of work.
"""

from .broker import LogBroker
from .event import Event, EventEnvelope
from .log import DeadLetter, EventLog, FileEventLog, InMemoryEventLog
from .ports import EventConsumer, EventHandler, EventPublisher, EventSubscriber, HasOutbox, Outbox
from .sql import SqlOutbox, SqlOutboxEvent

__all__ = [
    "DeadLetter",
    "Event",
    "EventConsumer",
    "EventEnvelope",
    "EventHandler",
    "EventLog",
    "EventPublisher",
    "EventSubscriber",
    "FileEventLog",
    "HasOutbox",
    "InMemoryEventLog",
    "LogBroker",
    "Outbox",
    "SqlOutbox",
    "SqlOutboxEvent",
]
