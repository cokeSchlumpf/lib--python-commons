"""Events with a transactional outbox: stored with the change that caused them, delivered at least once.

- **Events** (`Event`, `EventEnvelope`): immutable facts with a topic, a type and an optional ordering key.
- **Ports** (`Outbox`, `HasOutbox`, `EventPublisher`, `EventSubscriber`, `EventConsumer`, `EventHandler`).
- **Broker** (`LogBroker` on an `EventLog`: `InMemoryEventLog`, `FileEventLog`, `SqlEventLog`, `AzureBlobEventLog`): in-process, Kafka-like, single instance.
- **SQL outbox** (`SqlOutbox`, `SqlOutboxEvent`): the table ``outbox_events``, written in the caller's unit of work.
- **Relay and workers** (`OutboxRelay`, `BackgroundWorkers`, `CommitNotifyingUnitOfWorkFactory`): publish committed
  events and run the handlers in the application's lifespan, configured by `EventsSettings` (``[app.events]``) and
  wired with `background_workers_from_settings`.
"""

from .azure_blob import AzureBlobEventLog
from .broker import LogBroker
from .event import Event, EventEnvelope
from .log import DeadLetter, EventLog, FileEventLog, InMemoryEventLog
from .ports import EventConsumer, EventHandler, EventPublisher, EventSubscriber, HasOutbox, Outbox
from .relay import OutboxRelay
from .settings import (
    AzureBlobEventLogSettings,
    EventsSettings,
    SqlEventLogSettings,
    background_workers_from_settings,
)
from .sql import SqlOutbox, SqlOutboxEvent
from .sql_log import SqlEventLog
from .workers import BackgroundWorkers, CommitListener, CommitNotifyingUnitOfWorkFactory, Maintenance

__all__ = [
    "AzureBlobEventLog",
    "AzureBlobEventLogSettings",
    "BackgroundWorkers",
    "CommitListener",
    "CommitNotifyingUnitOfWorkFactory",
    "DeadLetter",
    "Event",
    "EventConsumer",
    "EventEnvelope",
    "EventHandler",
    "EventLog",
    "EventPublisher",
    "EventSubscriber",
    "EventsSettings",
    "FileEventLog",
    "HasOutbox",
    "InMemoryEventLog",
    "LogBroker",
    "Maintenance",
    "Outbox",
    "OutboxRelay",
    "SqlEventLog",
    "SqlEventLogSettings",
    "SqlOutbox",
    "SqlOutboxEvent",
    "background_workers_from_settings",
]
