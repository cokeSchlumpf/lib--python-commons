"""`TypedLiveStreams` and `PydanticCodec`: typed values over a byte-level `LiveStreams`."""

import asyncio
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from commons.streams import InMemoryLiveStreams, PydanticCodec, TypedLiveStreams


class _Progress(BaseModel):
    step: str
    done: int


class _Started(BaseModel):
    kind: Literal["started"] = "started"


class _Progressed(BaseModel):
    kind: Literal["progressed"] = "progressed"
    percent: int


class _Finished(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    kind: Literal["finished"] = "finished"
    result_id: str


type _Event = _Started | _Progressed | _Finished
_EventUnion = Annotated[_Started | _Progressed | _Finished, Field(discriminator="kind")]


def test_values_are_encoded_under_the_prefixed_key_and_decoded_back():
    backend = InMemoryLiveStreams()
    streams = TypedLiveStreams(backend, "test:progress", PydanticCodec[_Progress](_Progress))
    values = [_Progress(step="load", done=1), _Progress(step="save", done=2)]

    async def scenario():
        await streams.append("job-1", values)
        await streams.close("job-1")
        typed = [item async for item in streams.read("job-1")]
        raw = [item async for item in backend.read("test:progress:job-1")]
        return typed, raw

    typed, raw = asyncio.run(scenario())

    assert typed == [("1", values[0]), ("2", values[1])]
    assert raw[0] == ("1", b'{"step":"load","done":1}')


def test_every_member_of_a_discriminated_union_survives_the_stream():
    streams = TypedLiveStreams(InMemoryLiveStreams(), "test:events", PydanticCodec[_Event](_EventUnion))
    emitted: list[_Event] = [_Started(), _Progressed(percent=50), _Finished(result_id="r")]

    async def scenario():
        await streams.append("job-1", emitted)
        await streams.close("job-1")
        return [value async for _, value in streams.read("job-1")]

    assert asyncio.run(scenario()) == emitted


def test_values_are_encoded_with_their_aliases():
    codec = PydanticCodec[_Event](_EventUnion)

    event = codec.decode(b'{"kind":"finished","resultId":"r"}')

    assert event == _Finished(result_id="r")
    assert b'"resultId":"r"' in codec.encode(event)


def test_values_can_be_encoded_by_field_name():
    codec = PydanticCodec[_Event](_EventUnion, by_alias=False)

    assert b'"result_id":"r"' in codec.encode(_Finished(result_id="r"))
