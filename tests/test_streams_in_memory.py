"""`InMemoryLiveStreams`: replay and live reading, positions, waiting, closing and retention."""

import asyncio
import time

import pytest

from commons.streams import InMemoryLiveStreams

KEY = "test:stream"


async def _collect(streams: InMemoryLiveStreams, after: str | None = None, *, wait: bool = True, key: str = KEY):
    return [item async for item in streams.read(key, after, wait=wait)]


def _payloads(items) -> list[bytes]:
    return [payload for _, payload in items]


def test_a_closed_stream_is_read_from_the_start_with_positions():
    streams = InMemoryLiveStreams()

    async def scenario():
        await streams.append(KEY, [b"a", b"b"])
        await streams.append(KEY, [b"c"])
        await streams.close(KEY)
        return await _collect(streams)

    assert asyncio.run(scenario()) == [("1", b"a"), ("2", b"b"), ("3", b"c")]


def test_reading_after_a_position_resumes_there():
    streams = InMemoryLiveStreams()

    async def scenario():
        await streams.append(KEY, [b"a", b"b", b"c"])
        await streams.close(KEY)
        return await _collect(streams, after="2")

    assert _payloads(asyncio.run(scenario())) == [b"c"]


def test_streams_are_kept_apart_by_key():
    streams = InMemoryLiveStreams()

    async def scenario():
        await streams.append(KEY, [b"a"])
        await streams.append("other", [b"x"])
        await streams.close(KEY)
        return await _collect(streams)

    assert _payloads(asyncio.run(scenario())) == [b"a"]


def test_readers_get_new_payloads_live_until_the_stream_is_closed():
    streams = InMemoryLiveStreams()

    async def scenario():
        readers = [asyncio.create_task(_collect(streams)) for _ in range(2)]
        await asyncio.sleep(0)  # the readers wait for the stream to start
        await streams.append(KEY, [b"a"])
        await asyncio.sleep(0.01)
        await streams.append(KEY, [b"b"])
        await streams.close(KEY)
        async with asyncio.timeout(2):
            return await asyncio.gather(*readers)

    first, second = asyncio.run(scenario())

    assert first == second == [("1", b"a"), ("2", b"b")]  # fan-out: every reader gets every payload


def test_without_wait_a_missing_stream_ends_at_once():
    assert asyncio.run(_collect(InMemoryLiveStreams(), wait=False)) == []


def test_appending_to_a_closed_stream_raises():
    streams = InMemoryLiveStreams()

    async def scenario():
        await streams.close(KEY)
        await streams.close(KEY)  # closing twice is a no-op
        await streams.append(KEY, [b"late"])

    with pytest.raises(ValueError, match="closed"):
        asyncio.run(scenario())


def test_closed_streams_are_dropped_after_the_retention(monkeypatch):
    streams = InMemoryLiveStreams(retention=10)
    now = time.monotonic()
    monkeypatch.setattr(time, "monotonic", lambda: now)

    async def scenario():
        await streams.append(KEY, [b"a"])
        await streams.close(KEY)
        kept = await _collect(streams, wait=False)
        monkeypatch.setattr(time, "monotonic", lambda: now + 11)
        dropped = await _collect(streams, wait=False)
        return kept, dropped

    kept, dropped = asyncio.run(scenario())

    assert _payloads(kept) == [b"a"]
    assert dropped == []


def test_an_invalid_position_raises():
    with pytest.raises(ValueError, match="not a position"):
        asyncio.run(_collect(InMemoryLiveStreams(), after="x"))


# --- max_length ---------------------------------------------------------------------------------------------------


def test_max_length_keeps_the_newest_payloads_with_their_positions():
    streams = InMemoryLiveStreams(max_length=2)

    async def scenario():
        await streams.append(KEY, [b"a", b"b"])
        await streams.append(KEY, [b"c", b"d", b"e"])
        await streams.close(KEY)
        return await _collect(streams)

    assert asyncio.run(scenario()) == [("4", b"d"), ("5", b"e")]


def test_a_reader_behind_the_trimmed_part_continues_with_the_oldest_kept_payload():
    streams = InMemoryLiveStreams(max_length=2)

    async def scenario():
        await streams.append(KEY, [b"a", b"b", b"c", b"d"])
        await streams.close(KEY)
        return await _collect(streams, after="1"), await _collect(streams, after="3")

    behind, resumed = asyncio.run(scenario())
    assert behind == [("3", b"c"), ("4", b"d")]
    assert resumed == [("4", b"d")]


def test_a_live_reader_that_falls_behind_continues_after_the_trimmed_part():
    streams = InMemoryLiveStreams(max_length=1)

    async def scenario():
        await streams.append(KEY, [b"a"])
        reader = streams.read(KEY)
        first = await anext(reader)
        await streams.append(KEY, [b"b", b"c"])  # "b" is trimmed before the reader gets to it
        await streams.close(KEY)
        return [first] + [item async for item in reader]

    assert asyncio.run(scenario()) == [("1", b"a"), ("3", b"c")]


def test_without_max_length_every_payload_is_kept():
    streams = InMemoryLiveStreams()

    async def scenario():
        await streams.append(KEY, [bytes([i % 256]) for i in range(1000)])
        await streams.close(KEY)
        return await _collect(streams)

    assert len(asyncio.run(scenario())) == 1000


@pytest.mark.parametrize("max_length", [0, -1])
def test_max_length_must_be_at_least_one(max_length):
    with pytest.raises(ValueError, match="max_length"):
        InMemoryLiveStreams(max_length=max_length)
