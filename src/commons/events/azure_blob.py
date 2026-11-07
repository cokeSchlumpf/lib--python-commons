import json
from contextlib import suppress

try:
    from azure.core import MatchConditions
    from azure.core.exceptions import (
        HttpResponseError,
        ResourceExistsError,
        ResourceModifiedError,
        ResourceNotFoundError,
    )
    from azure.storage.blob import BlobClient, ContainerClient
except ImportError:
    # Azure's packages are the extra `azure`, as in `commons.storage.azure`.
    pass

from commons.datetime_operators import utc_now

from .event import EventEnvelope
from .log import _checked

_SEGMENT_SHIFT = 40
"""An offset is ``segment << 40 | position``: a position in a segment's bytes fits in 40 bits (1 TB)."""

_POSITION_MASK = (1 << _SEGMENT_SHIFT) - 1

_MAX_BLOCKS = 49_000
"""When a segment moves on: an append blob takes 50,000 blocks, and each event is one block."""

_READ_SIZE = 4 * 1024 * 1024


class AzureBlobEventLog:
    """An `EventLog` in append blobs of an Azure Storage container, durable across restarts.

    ```text
    topics/<topic>/<segment>.jsonl                one envelope per line, one block per line
    _offsets/<group>/<topic>.json                 committed offset of the group
    _dead_letters/<group>/<topic>.jsonl           events the group failed to process
    ```

    A topic continues in a new segment before its blob is full. The old one is sealed first, and a reader moves on
    only from a sealed blob: a sealed blob can't grow, so no event can appear behind a reader, even if a second
    instance was still writing to the old segment.

    Args:
        container_client: The container of the log; created if it doesn't exist.
        max_blocks: The number of blocks after which a segment is sealed.
    """

    def __init__(self, container_client: "ContainerClient", *, max_blocks: int = _MAX_BLOCKS) -> None:
        self._container = container_client
        self._max_blocks = max_blocks
        self._segments: dict[str, int] = {}
        with suppress(ResourceExistsError):
            container_client.create_container()

    def append(self, envelope: EventEnvelope) -> None:
        topic = envelope.topic
        data = (envelope.model_dump_json() + "\n").encode("utf-8")
        segment = self._current_segment(topic)

        while True:
            blob = self._segment_blob(topic, segment)
            try:
                result = _append(blob, data)
            except HttpResponseError as e:
                if getattr(e, "error_code", None) != "BlobIsSealed":  # set by the storage client
                    raise
                segment += 1  # another instance moved on
                self._segments[topic] = segment
                continue

            if result["blob_committed_block_count"] >= self._max_blocks:
                blob.seal_append_blob()
                self._segments[topic] = segment + 1
            return

    def read(self, topic: str, offset: int, limit: int) -> list[tuple[EventEnvelope, int]]:
        segment, position = offset >> _SEGMENT_SHIFT, offset & _POSITION_MASK
        events: list[tuple[EventEnvelope, int]] = []

        while len(events) < limit:
            blob = self._segment_blob(topic, segment)
            try:
                properties = blob.get_blob_properties()
            except ResourceNotFoundError:
                break

            if position >= properties.size:
                if not properties.is_append_blob_sealed:
                    break
                segment, position = segment + 1, 0
                continue

            for line in _lines(blob, position, properties.size):
                position += len(line)
                events.append((EventEnvelope.model_validate_json(line), segment << _SEGMENT_SHIFT | position))
                if len(events) == limit:
                    break

        return events

    def committed_offset(self, group: str, topic: str) -> int:
        blob = self._container.get_blob_client(_offset_name(group, topic))
        try:
            return int(json.loads(blob.download_blob().readall())["offset"])
        except ResourceNotFoundError:
            return 0

    def commit_offset(self, group: str, topic: str, offset: int) -> None:
        blob = self._container.get_blob_client(_offset_name(group, topic))
        blob.upload_blob(json.dumps({"offset": offset}).encode("utf-8"), overwrite=True)

    def dead_letter(self, group: str, envelope: EventEnvelope, error: str) -> None:
        # shortcut: one blob per group and topic, so at most 50,000 dead letters; upgrade if there are ever that many.
        entry = {
            "dead_lettered_at": utc_now().isoformat(),
            "error": error,
            "envelope": envelope.model_dump(mode="json"),
        }
        name = f"_dead_letters/{_checked(group)}/{_checked(envelope.topic)}.jsonl"
        _append(self._container.get_blob_client(name), (json.dumps(entry) + "\n").encode("utf-8"))

    def _segment_blob(self, topic: str, segment: int) -> "BlobClient":
        return self._container.get_blob_client(f"topics/{_checked(topic)}/{segment:010d}.jsonl")

    def _current_segment(self, topic: str) -> int:
        """The newest segment of the topic: from the listing once per instance, then kept while appending."""
        if topic not in self._segments:
            blobs = self._container.list_blobs(name_starts_with=f"topics/{_checked(topic)}/")
            numbers = [int(blob.name.rsplit("/", 1)[1].removesuffix(".jsonl")) for blob in blobs]
            self._segments[topic] = max(numbers, default=0)
        return self._segments[topic]


def _offset_name(group: str, topic: str) -> str:
    return f"_offsets/{_checked(group)}/{_checked(topic)}.json"


def _append(blob: "BlobClient", data: bytes) -> dict:
    """Append one block, atomically, creating the blob if it doesn't exist (and never replacing one that does)."""
    try:
        return blob.append_block(data)
    except ResourceNotFoundError:
        with suppress(ResourceExistsError, ResourceModifiedError):
            blob.create_append_blob(match_condition=MatchConditions.IfMissing)
        return blob.append_block(data)


def _lines(blob: "BlobClient", position: int, size: int) -> list[bytes]:
    """The complete lines from ``position`` on: as many as the first bytes hold, at least one."""
    length = min(_READ_SIZE, size - position)
    while True:
        data = blob.download_blob(offset=position, length=length).readall()
        lines = data.splitlines(keepends=True)
        complete = [line for line in lines if line.endswith(b"\n")]
        if complete or length >= size - position:
            return complete
        length = min(length * 2, size - position)
