import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from commons.datetime_operators import utc_now

from .event import EventEnvelope


class EventLog(Protocol):
    """The storage of a `LogBroker`: append-only topic logs plus the offsets of the consumer groups.

    An offset is an opaque position in a topic's log: ``0`` is its start, and every event read comes with the offset
    right after it, the one to commit once the event is processed.
    """

    def append(self, envelope: EventEnvelope) -> None:
        """Durably append the envelope to the log of its topic."""
        ...

    def read(self, topic: str, offset: int, limit: int) -> list[tuple[EventEnvelope, int]]:
        """Return at most ``limit`` events of ``topic`` from ``offset`` on, each with its next offset."""
        ...

    def committed_offset(self, group: str, topic: str) -> int:
        """Return the offset ``group`` committed for ``topic``; ``0`` if it never did."""
        ...

    def commit_offset(self, group: str, topic: str, offset: int) -> None:
        """Store ``offset`` as the position ``group`` continues ``topic`` from."""
        ...

    def dead_letter(self, group: str, envelope: EventEnvelope, error: str) -> None:
        """Keep an envelope that ``group`` failed to process, for manual inspection."""
        ...


@dataclass(frozen=True)
class DeadLetter:
    """An event a consumer group failed to process, with the error."""

    group: str
    envelope: EventEnvelope
    error: str


class InMemoryEventLog:
    """An `EventLog` in process memory, for tests and development; everything is lost on restart.

    The offset of an event is its index in the topic's list, plus one.
    """

    def __init__(self) -> None:
        self.topics: dict[str, list[EventEnvelope]] = {}
        self.offsets: dict[tuple[str, str], int] = {}
        self.dead_letters: list[DeadLetter] = []

    def append(self, envelope: EventEnvelope) -> None:
        self.topics.setdefault(envelope.topic, []).append(envelope)

    def read(self, topic: str, offset: int, limit: int) -> list[tuple[EventEnvelope, int]]:
        events = self.topics.get(topic, [])[offset : offset + limit]
        return [(envelope, offset + i + 1) for i, envelope in enumerate(events)]

    def committed_offset(self, group: str, topic: str) -> int:
        return self.offsets.get((group, topic), 0)

    def commit_offset(self, group: str, topic: str, offset: int) -> None:
        self.offsets[(group, topic)] = offset

    def dead_letter(self, group: str, envelope: EventEnvelope, error: str) -> None:
        self.dead_letters.append(DeadLetter(group, envelope, error))


_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def _checked(name: str) -> str:
    """Return the name if it is safe as a file name, else raise `ValueError`."""

    if not _NAME.match(name):
        raise ValueError(f"`{name}` is not a valid topic or consumer group name.")

    return name


class FileEventLog:
    """An `EventLog` in plain files below ``root``, durable across restarts.

    ```text
    <root>/<topic>.jsonl                          one envelope per line, append-only
    <root>/_offsets/<group>/<topic>.json          committed offset of the group
    <root>/_dead_letters/<group>/<topic>.jsonl    events the group failed to process
    ```

    The offset of an event is the byte position after its line. A line without its trailing newline (an append cut
    short by a crash) is never read.

    Single process only: appends and offset files are not locked.

    Args:
        root: The directory of the log.
    """

    def __init__(self, root: Path) -> None:
        self.root = root

    def append(self, envelope: EventEnvelope) -> None:
        path = self._topic_path(envelope.topic)
        path.parent.mkdir(parents=True, exist_ok=True)
        line = envelope.model_dump_json() + "\n"

        with path.open("ab") as file:
            file.write(line.encode("utf-8"))
            file.flush()
            os.fsync(file.fileno())

    def read(self, topic: str, offset: int, limit: int) -> list[tuple[EventEnvelope, int]]:
        path = self._topic_path(topic)
        if not path.exists():
            return []

        events: list[tuple[EventEnvelope, int]] = []
        with path.open("rb") as file:
            file.seek(offset)
            while len(events) < limit:
                line = file.readline()
                if not line.endswith(b"\n"):
                    break
                offset += len(line)
                events.append((EventEnvelope.model_validate_json(line), offset))

        return events

    def committed_offset(self, group: str, topic: str) -> int:
        path = self._offset_path(group, topic)
        if not path.exists():
            return 0

        return int(json.loads(path.read_text())["offset"])

    def commit_offset(self, group: str, topic: str, offset: int) -> None:
        path = self._offset_path(group, topic)
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(".tmp")
        temp.write_text(json.dumps({"offset": offset}))
        temp.replace(path)  # atomic: a crash leaves the old or the new offset

    def dead_letter(self, group: str, envelope: EventEnvelope, error: str) -> None:
        path = self.root / "_dead_letters" / _checked(group) / f"{_checked(envelope.topic)}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "dead_lettered_at": utc_now().isoformat(),
            "error": error,
            "envelope": envelope.model_dump(mode="json"),
        }

        with path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(entry) + "\n")

    def _topic_path(self, topic: str) -> Path:
        return self.root / f"{_checked(topic)}.jsonl"

    def _offset_path(self, group: str, topic: str) -> Path:
        return self.root / "_offsets" / _checked(group) / f"{_checked(topic)}.json"
