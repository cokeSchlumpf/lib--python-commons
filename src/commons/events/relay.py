import asyncio
import logging
from contextlib import suppress
from datetime import timedelta

from commons.database import UnitOfWorkFactory
from commons.datetime_operators import utc_now

from .ports import EventPublisher, HasOutbox


LOG = logging.getLogger(__name__)


class OutboxRelay:
    """Publishes the events of the outbox and marks them published.

    The only component that publishes: `run` relays everything unpublished at start (events left over from a crash),
    then again whenever `wake` is called (after a commit) or ``poll_interval`` seconds passed. An event is marked
    published only after the broker accepted it, so a crash in between publishes it again: at least once. Events are
    published in the order they were added.

    Single application instance only: several relays would publish the same events. With several instances, claim
    rows with ``SELECT ... FOR UPDATE SKIP LOCKED`` (or elect one leader) before publishing.

    Args:
        repositories: Opens the units of work to read and update the outbox with.
        publisher: The broker the events are published to.
        poll_interval: Seconds between relays when the relay was not woken.
        batch_size: The maximum number of events read from the outbox at once.
        retention: How long published events are kept in the outbox before `prune` deletes them.
    """

    def __init__(
        self,
        repositories: UnitOfWorkFactory[HasOutbox],
        publisher: EventPublisher,
        *,
        poll_interval: float = 5.0,
        batch_size: int = 100,
        retention: timedelta = timedelta(days=7),
    ) -> None:
        self._repositories = repositories
        self._publisher = publisher
        self._poll_interval = poll_interval
        self._batch_size = batch_size
        self._retention = retention
        self._loop: asyncio.AbstractEventLoop | None = None
        self._wake: asyncio.Event | None = None

    def wake(self) -> None:
        """Relay now instead of at the next poll; safe to call from any thread."""

        loop, wake = self._loop, self._wake
        if loop is not None and wake is not None:
            with suppress(RuntimeError):  # loop closed meanwhile
                loop.call_soon_threadsafe(wake.set)

    async def run(self) -> None:
        """Relay until cancelled; a failed relay is logged and retried at the next poll."""

        self._loop = asyncio.get_running_loop()
        self._wake = wake = asyncio.Event()
        try:
            while True:
                wake.clear()  # before relaying, so a commit during it is not missed
                try:
                    await self.relay_pending()
                except Exception:
                    LOG.exception("Relaying outbox events failed; retrying")

                with suppress(TimeoutError):
                    await asyncio.wait_for(wake.wait(), self._poll_interval)
        finally:
            self._loop = self._wake = None

    async def relay_pending(self) -> int:
        """Publish all unpublished events, oldest first; return how many were published."""

        total = 0

        while True:
            with self._repositories.for_system() as (repositories, _):
                batch = repositories.outbox.list_unpublished(self._batch_size)

            if not batch:
                return total

            published: list[str] = []
            try:
                for envelope in batch:
                    await self._publisher.publish(envelope)
                    published.append(envelope.event_id)
            finally:
                if published:
                    with self._repositories.for_system() as (repositories, commit):
                        repositories.outbox.mark_published(published, utc_now())
                        await commit()
                    total += len(published)

    async def prune(self) -> int:
        """Delete the events published longer ago than the retention; return how many."""

        with self._repositories.for_system() as (repositories, commit):
            deleted = repositories.outbox.delete_published_before(utc_now() - self._retention)
            await commit()

        return deleted
