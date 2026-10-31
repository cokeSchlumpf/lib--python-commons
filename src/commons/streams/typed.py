from collections.abc import AsyncIterator
from typing import Any, Protocol

from pydantic import TypeAdapter

from .live_streams import LiveStreams


class Codec[T](Protocol):
    """Turns values into the payloads of a `LiveStreams` stream and back."""

    def encode(self, value: T) -> bytes: ...

    def decode(self, data: bytes) -> T: ...


class PydanticCodec[T]:
    """Encodes values as JSON with a Pydantic ``TypeAdapter``: models, and discriminated unions of models.

    Args:
        type_: The type to validate decoded values with, e.g. a model or a discriminated union of models;
            it may be wider than ``T`` (decoding a union member as its base class).
        by_alias: Whether to encode fields by their alias, e.g. camelCase names.

    Example:
        ```python
        class Started(BaseModel):
            kind: Literal["started"] = "started"


        class Progressed(BaseModel):
            kind: Literal["progressed"] = "progressed"
            percent: int


        Progress = Annotated[Started | Progressed, Field(discriminator="kind")]

        codec = PydanticCodec[Started | Progressed](Progress)
        codec.encode(Progressed(percent=50))  # b'{"kind":"progressed","percent":50}'
        ```
    """

    def __init__(self, type_: Any, *, by_alias: bool = True) -> None:
        self._adapter: TypeAdapter[T] = TypeAdapter(type_)
        self._by_alias = by_alias

    def encode(self, value: T) -> bytes:
        return self._adapter.dump_json(value, by_alias=self._by_alias)

    def decode(self, data: bytes) -> T:
        return self._adapter.validate_json(data)


class TypedLiveStreams[T]:
    """A type-safe view on one kind of stream of a `LiveStreams`: values of ``T``, by id, under a key prefix.

    The stream of ``id`` is the `LiveStreams` stream ``f"{prefix}:{id}"``, so several kinds of streams, also an
    application's own, can share one backend.

    Args:
        streams: The backend.
        prefix: The key prefix of this kind of stream, e.g. ``"myapp:progress"``.
        codec: Encodes and decodes the values.
    """

    def __init__(self, streams: LiveStreams, prefix: str, codec: Codec[T]) -> None:
        self._streams = streams
        self._prefix = prefix
        self._codec = codec

    async def append(self, id: str, values: list[T]) -> None:
        """Append the values to the stream of ``id``; see `LiveStreams.append`."""

        await self._streams.append(self._key(id), [self._codec.encode(value) for value in values])

    async def close(self, id: str) -> None:
        """Close the stream of ``id``; see `LiveStreams.close`."""

        await self._streams.close(self._key(id))

    async def read(self, id: str, after: str | None = None, *, wait: bool = True) -> AsyncIterator[tuple[str, T]]:
        """Read the stream of ``id``, decoded; see `LiveStreams.read`."""

        async for position, payload in self._streams.read(self._key(id), after, wait=wait):
            yield position, self._codec.decode(payload)

    def _key(self, id: str) -> str:
        return f"{self._prefix}:{id}"
