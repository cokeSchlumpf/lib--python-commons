import asyncio
import logging
from collections.abc import Awaitable, Callable

from commons.database import CommitFunction, UnitOfWork, UnitOfWorkFactory
from commons.users import User

from .event import Event
from .ports import EventConsumer, EventHandler
from .relay import OutboxRelay


LOG = logging.getLogger(__name__)

_RESTART_DELAY_SECONDS = 5.0

_STOP_TIMEOUT_SECONDS = 10.0


type Maintenance = Callable[[], Awaitable[object]]
"""A periodic maintenance job, e.g. failing stale runs."""


class BackgroundWorkers:
    """The background tasks of the (single) application instance, started and stopped by its lifespan.

    - the outbox relay, publishing committed events,
    - the event consumer, executing the handlers subscribed with `subscribe`,
    - maintenance: pruning the outbox and the given ``maintenance`` jobs, at start and every
      ``maintenance_interval`` seconds.

    A task that crashes is logged and restarted, so one failure cannot silently stop event processing.

    Args:
        relay: Publishes the events of the outbox.
        consumer: Delivers the published events to their handlers.
        maintenance: Further periodic jobs, run after the outbox is pruned.
        maintenance_interval: Seconds between maintenance runs.
    """

    def __init__(
        self,
        relay: OutboxRelay,
        consumer: EventConsumer,
        *,
        maintenance: list[Maintenance] | None = None,
        maintenance_interval: float = 60.0,
    ) -> None:
        self._relay = relay
        self._consumer = consumer
        self._maintenance = list(maintenance or [])
        self._maintenance_interval = maintenance_interval
        self._tasks: list[asyncio.Task] = []

    def subscribe[E: Event](self, *, group: str, event_type: type[E], handler: EventHandler[E]) -> None:
        """Let consumer ``group`` process the events of ``event_type`` with ``handler``.

        Raises:
            RuntimeError: If the workers are already running; subscribe before `start`.
            ValueError: If ``group`` already has a handler for ``event_type``.
        """

        if self._tasks:
            raise RuntimeError("Subscribe before the background workers are started.")

        self._consumer.subscribe(group=group, event_type=event_type, handler=handler)

    def start(self) -> None:
        """Start all tasks on the running event loop."""

        if self._tasks:
            raise RuntimeError("Background workers are already running.")

        self._tasks = [
            asyncio.create_task(_supervised(name, work), name=name)
            for name, work in [
                ("outbox-relay", self._relay.run),
                ("event-consumer", self._consumer.run),
                ("maintenance", self._maintain),
            ]
        ]

    async def stop(self, timeout: float = _STOP_TIMEOUT_SECONDS) -> None:
        """Cancel all tasks and wait until they ended, at most ``timeout`` seconds.

        A task still running is cancelled again every half second: a library in a handler (e.g. anyio in an LLM
        client) may swallow a cancellation, and the task's loop then carries on. Tasks left after ``timeout`` are
        logged and abandoned, so a stuck task never blocks the shutdown.
        """

        tasks, self._tasks = self._tasks, []
        pending = set(tasks)
        deadline = asyncio.get_running_loop().time() + timeout

        while pending:
            for task in pending:
                task.cancel()
            _, pending = await asyncio.wait(pending, timeout=0.5)

            if pending and asyncio.get_running_loop().time() >= deadline:
                names = ", ".join(sorted(task.get_name() for task in pending))
                LOG.error(f"Background tasks did not stop within {timeout}s: {names}")
                return

    async def maintain(self) -> None:
        """Prune the outbox and run the maintenance jobs once."""

        await self._relay.prune()
        for job in self._maintenance:
            await job()

    async def _maintain(self) -> None:
        while True:
            try:
                await self.maintain()
            except Exception:
                LOG.exception("Maintenance failed; retrying")
            await asyncio.sleep(self._maintenance_interval)


async def _supervised(name: str, work: Callable[[], Awaitable[None]]) -> None:
    """Run ``work`` until cancelled, restarting it after a crash."""

    while True:
        try:
            await work()
            return
        except Exception:
            LOG.exception(f"Background task `{name}` crashed; restarting in {_RESTART_DELAY_SECONDS:.0f}s")
            await asyncio.sleep(_RESTART_DELAY_SECONDS)


type CommitListener = Callable[[], None]
"""Called after a successful commit, e.g. `OutboxRelay.wake`."""


def _notifying(commit: CommitFunction, listeners: list[CommitListener]) -> CommitFunction:
    """Return ``commit``, followed by calling every listener."""

    async def commit_and_notify() -> None:
        await commit()
        for listener in listeners:
            try:
                listener()
            except Exception:
                LOG.exception("Commit listener failed")

    return commit_and_notify


class _CommitNotifyingUnitOfWork[T](UnitOfWork[T]):
    def __init__(self, inner: UnitOfWork[T], listeners: list[CommitListener]) -> None:
        self._inner = inner
        self._listeners = listeners

    def __enter__(self) -> tuple[T, CommitFunction]:
        repositories, commit = self._inner.__enter__()
        return repositories, _notifying(commit, self._listeners)

    def __exit__(self, *args: object) -> None:
        self._inner.__exit__(*args)


class CommitNotifyingUnitOfWorkFactory[T](UnitOfWorkFactory[T]):
    """Wraps a `UnitOfWorkFactory` to call listeners after every successful commit.

    Lets the outbox relay publish events right after the transaction that stored them, without domain functions
    having to know about the relay. A failing listener is logged and never fails the (already committed) unit of
    work.

    Args:
        inner: The wrapped factory.
    """

    def __init__(self, inner: UnitOfWorkFactory[T]) -> None:
        self._inner = inner
        self._listeners: list[CommitListener] = []

    def add_commit_listener(self, listener: CommitListener) -> None:
        """Call ``listener`` after every successful commit."""

        self._listeners.append(listener)

    def for_user(self, user: User) -> UnitOfWork[T]:
        return _CommitNotifyingUnitOfWork(self._inner.for_user(user), self._listeners)

    def for_system(self) -> UnitOfWork[T]:
        return _CommitNotifyingUnitOfWork(self._inner.for_system(), self._listeners)

    def __enter__(self) -> tuple[T, CommitFunction]:
        """Open a unit of work like entering the wrapped factory (for its current user), with notifying commit."""
        repositories, commit = self._inner.__enter__()
        return repositories, _notifying(commit, self._listeners)

    def __exit__(self, *args: object) -> None:
        self._inner.__exit__(*args)
