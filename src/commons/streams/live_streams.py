import asyncio
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Protocol


class LiveStreams(Protocol):
    """Short-lived streams of opaque payloads, by key, read by every current reader (fan-out).

    Writers append payloads to a stream; any number of readers, on any application instance, read them from a
    position on. Streams are not durable: they carry live views, such as the events of a running job, while the state they
    show is stored elsewhere. A closed stream stays readable for a while, for late readers and reconnects, and then
    disappears. Use `TypedLiveStreams` for a type-safe view on one kind of stream.

    Positions are opaque strings, increasing within a stream, e.g. to resume a reader with SSE's ``Last-Event-ID``.
    """

    async def append(self, key: str, payloads: list[bytes]) -> None:
        """Append the payloads to the stream, which is created by the first append.

        Raises:
            ValueError: If the stream is closed.
        """
        ...

    async def close(self, key: str) -> None:
        """Mark the stream finished: readers stop after its last payload. Closing twice is a no-op."""
        ...

    def read(self, key: str, after: str | None = None, *, wait: bool = True) -> AsyncIterator[tuple[str, bytes]]:
        """Return the payloads of the stream after the position ``after`` (all if None), then the new ones live, each
        with its position, until the stream is closed.

        With ``wait``, a stream that does not exist yet is waited for; without, the iterator ends at once.

        Raises:
            ValueError: If ``after`` is not a position of this kind of stream.
        """
        ...


@dataclass
class _Stream:
    payloads: list[bytes] = field(default_factory=list)
    closed_at: float | None = None


class InMemoryLiveStreams:
    """A `LiveStreams` in process memory: readers on the same application instance only.

    Payloads are kept as the bytes they were appended as, so values go through their codec as with any other
    backend. The position of a payload is its number in the stream, starting at ``"1"``. A closed stream is kept
    for ``retention`` seconds, then dropped on the next access. A Redis adapter would replace this for several
    instances.

    Args:
        retention: Seconds a closed stream stays readable.
    """

    def __init__(self, *, retention: float = 300.0) -> None:
        self._retention = retention
        self._streams: dict[str, _Stream] = {}
        self._waiters: set[asyncio.Event] = set()

    async def append(self, key: str, payloads: list[bytes]) -> None:
        self._prune()
        stream = self._streams.setdefault(key, _Stream())
        if stream.closed_at is not None:
            raise ValueError(f"The stream `{key}` is closed.")

        stream.payloads.extend(payloads)
        self._notify()

    async def close(self, key: str) -> None:
        stream = self._streams.setdefault(key, _Stream())
        if stream.closed_at is None:
            stream.closed_at = time.monotonic()
            self._notify()

    async def read(self, key: str, after: str | None = None, *, wait: bool = True) -> AsyncIterator[tuple[str, bytes]]:
        position = _position(after)

        while True:
            self._prune()
            stream = self._streams.get(key)
            if stream is None and not wait:
                return

            if stream is not None:
                while position < len(stream.payloads):
                    position += 1
                    yield str(position), stream.payloads[position - 1]

                if stream.closed_at is not None:
                    return

            await self._changed()

    async def _changed(self) -> None:
        """Wait until a stream changes."""

        waiter = asyncio.Event()  # created per wait, so it belongs to the reader's event loop
        self._waiters.add(waiter)
        try:
            await waiter.wait()
        finally:
            self._waiters.discard(waiter)

    def _notify(self) -> None:
        for waiter in self._waiters:
            waiter.set()

    def _prune(self) -> None:
        now = time.monotonic()
        for key, stream in list(self._streams.items()):
            if stream.closed_at is not None and now - stream.closed_at > self._retention:
                del self._streams[key]


def _position(after: str | None) -> int:
    if after is None:
        return 0

    if not after.isdigit():
        raise ValueError(f"`{after}` is not a position of an in-memory live stream.")

    return int(after)
