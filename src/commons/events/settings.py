from datetime import timedelta
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from commons.database import UnitOfWorkFactory
from commons.settings import AppSettings, read_settings_object

from .broker import LogBroker
from .log import EventLog, FileEventLog, InMemoryEventLog
from .ports import HasOutbox
from .relay import OutboxRelay
from .workers import BackgroundWorkers, CommitNotifyingUnitOfWorkFactory, Maintenance


class EventsSettings(BaseModel):
    """The settings of the message broker, the outbox relay and the maintenance, read from ``[app.events]``.

    Attributes:
        mode: ``file``: durable topic logs below ``dir``; ``memory``: lost on restart (tests, development).
        dir: The directory of the ``file`` broker; defaults to ``<data_dir>/events``.
        poll_interval_seconds: How often the relay and the consumers look for work they were not woken for.
        handler_max_concurrency: How many event handlers of one consumer group may run at the same time, for events with different keys.
        handler_max_attempts: How often an event handler is tried before the event is dead-lettered.
        outbox_retention_days: How long published events are kept in the outbox.
        maintenance_interval_seconds: How often the outbox is pruned and the maintenance jobs run.

    Example:
        ```toml
        [app.events]
        mode = "file"
        poll_interval_seconds = 5
        handler_max_attempts = 3
        ```
    """

    model_config = ConfigDict(extra="forbid")

    mode: Literal["file", "memory"] = "file"
    dir: Path | None = None
    poll_interval_seconds: float = Field(default=5.0, gt=0)
    handler_max_concurrency: int = Field(default=10, gt=0)
    handler_max_attempts: int = Field(default=3, gt=0)
    outbox_retention_days: int = Field(default=7, gt=0)
    maintenance_interval_seconds: float = Field(default=60.0, gt=0)

    @property
    def outbox_retention(self) -> timedelta:
        return timedelta(days=self.outbox_retention_days)

    def events_dir(self) -> Path:
        """Return the directory of the ``file`` broker."""

        return self.dir or AppSettings.read().data_dir / "events"

    @staticmethod
    def read() -> "EventsSettings":
        """Read the settings from ``[app.events]``; the defaults if the section is missing."""

        try:
            return read_settings_object("events", EventsSettings)
        except KeyError:
            return EventsSettings()


def background_workers_from_settings(
    repositories: UnitOfWorkFactory[HasOutbox],
    settings: EventsSettings | None = None,
    maintenance: list[Maintenance] | None = None,
) -> BackgroundWorkers:
    """Wire the message broker, the outbox relay and the event consumer.

    The broker is selected by ``[app.events] mode``. If ``repositories`` signals commits (a
    `CommitNotifyingUnitOfWorkFactory`), the relay publishes right after every commit; otherwise it relies on
    polling. Subscribe the event handlers with `BackgroundWorkers.subscribe` before starting the workers.

    Args:
        repositories: Opens the units of work whose repositories contain the outbox.
        settings: The settings. Read from ``[app.events]`` if not given.
        maintenance: Further periodic jobs, run after the outbox is pruned.
    """

    settings = settings or EventsSettings.read()

    log: EventLog = FileEventLog(settings.events_dir()) if settings.mode == "file" else InMemoryEventLog()
    broker = LogBroker(
        log,
        poll_interval=settings.poll_interval_seconds,
        max_concurrency=settings.handler_max_concurrency,
        max_attempts=settings.handler_max_attempts,
    )
    relay = OutboxRelay(
        repositories,
        broker,
        poll_interval=settings.poll_interval_seconds,
        retention=settings.outbox_retention,
    )

    if isinstance(repositories, CommitNotifyingUnitOfWorkFactory):
        repositories.add_commit_listener(relay.wake)

    return BackgroundWorkers(
        relay,
        broker,
        maintenance=maintenance,
        maintenance_interval=settings.maintenance_interval_seconds,
    )
