# Live streams

Short-lived streams of payloads by key, read by every current reader: a live view of something that happens now, e.g. the progress of a job or the tokens of an answer. Delivery is **at most once** and not durable: the state a stream shows is stored elsewhere.

## Quickstart

```python
from pydantic import BaseModel

from commons.streams import InMemoryLiveStreams, PydanticCodec, TypedLiveStreams


class Progress(BaseModel):
    step: str
    done: int


live_streams = InMemoryLiveStreams()  # one backend per application
progress = TypedLiveStreams(live_streams, "myapp:progress", PydanticCodec[Progress](Progress))

# The worker:
await progress.append(job_id, [Progress(step="load", done=1)])
await progress.close(job_id)

# Any number of readers, e.g. an SSE endpoint:
async for position, value in progress.read(job_id): ...
```

## Concepts

- **Live streams** (`LiveStreams`): streams of byte payloads, by key. Writers append; every reader gets every payload from where it starts reading. One backend serves all kinds of streams.
- **Typed live streams** (`TypedLiveStreams[T]` with a `Codec[T]`): a type-safe view on one kind of stream: values of `T` by id, under a key prefix, encoded e.g. as JSON with `PydanticCodec`.
- **Position**: an opaque string per payload, increasing within a stream, e.g. the `id` of an SSE event, so a reader resumes with `Last-Event-ID`.

## Configuration

`InMemoryLiveStreams(retention=300.0)`: seconds a closed stream stays readable, for late readers and reconnects.

## Usage

- **Choose a prefix of your own** (e.g. `myapp:progress`), so streams of different kinds, also those of libraries, do not collide on one backend.
- **Close the stream when the work is done**; readers then stop after its last payload.
- **Resume a reader** with the last position it saw: `read(id, after=position)`.
- **Encode several kinds of values** in one stream with a discriminated union: `PydanticCodec[Event](Annotated[Started | Progressed, Field(discriminator="kind")])`; `by_alias=False` encodes field names instead of aliases.
- **Don't wait for a stream that may never come**: `read(id, wait=False)` ends at once if the stream doesn't exist.
- **Treat streaming as best effort.** If appending fails, the work goes on and its result is stored; only the live view is missing.

## Behavior

- **From the start, or resumed.** Without `after`, a reader gets all payloads of the stream, also when it connects late; with `after`, only those after that position.
- **Missing streams are waited for**, unless `wait=False`: a reader may connect before the writer started.
- **The stream ends** for its readers when it is closed. A closed stream is kept for `retention` seconds, then disappears; reading it then waits for a new stream, or ends with `wait=False`.
- **Single application instance.** `InMemoryLiveStreams` only serves readers in the same process; a Redis adapter would serve several instances.

## Errors

| Exception | Raised when | What to do |
| --- | --- | --- |
| `ValueError` | `append` to a closed stream. | Use a new key for new work. |
| `ValueError` (while reading) | `after` is not a position of this kind of stream. | Answer 400, or read without `after`. |

## API reference

::: commons.streams
