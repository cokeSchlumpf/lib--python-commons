"""Live streams: short-lived streams of payloads by key, fanned out to every current reader, at most once.

- **Port** (`LiveStreams`) and its in-process adapter (`InMemoryLiveStreams`, single application instance).
- **Typed view** (`TypedLiveStreams` with a `Codec`, e.g. `PydanticCodec`): values of one type under a key prefix.

Not durable: a live stream shows state that is stored elsewhere, e.g. the progress of a job, while it happens.
"""

from .live_streams import InMemoryLiveStreams, LiveStreams
from .typed import Codec, PydanticCodec, TypedLiveStreams

__all__ = [
    "Codec",
    "InMemoryLiveStreams",
    "LiveStreams",
    "PydanticCodec",
    "TypedLiveStreams",
]
