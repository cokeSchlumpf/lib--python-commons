"""The event logs that survive a restart: `SqlEventLog` and `AzureBlobEventLog` (T-011)."""

import threading
from collections.abc import Callable
from pathlib import Path
from typing import ClassVar

import pytest
from sqlalchemy.dialects import mssql
from sqlalchemy.schema import CreateTable
from sqlmodel import SQLModel, create_engine

from commons.events import (
    AzureBlobEventLog,
    Event,
    EventEnvelope,
    EventLog,
    FileEventLog,
    InMemoryEventLog,
    SqlEventLog,
)
from commons.events.sql_log import _Model

from tests.fake_blob_container import FakeContainer

GROUP = "test-group"


class _Requested(Event):
    topic: ClassVar[str] = "test"
    event_type: ClassVar[str] = "requested"

    name: str = "ä"


def _envelope(name: str = "ä") -> EventEnvelope:
    return _Requested(name=name).to_envelope()


def _names(events: list[tuple[EventEnvelope, int]]) -> list[str]:
    return [envelope.payload["name"] for envelope, _ in events]


@pytest.fixture(params=["sql", "azure_blob", "file", "memory"])
def new_log(request, tmp_path: Path) -> Callable[[], EventLog]:
    """Builds a log on the same storage each time, like a new instance of the app."""
    engine = create_engine(f"sqlite:///{tmp_path / 'log.db'}")
    container = FakeContainer()
    memory = InMemoryEventLog()
    return {
        "sql": lambda: SqlEventLog(engine),
        "azure_blob": lambda: AzureBlobEventLog(container),
        "file": lambda: FileEventLog(tmp_path),
        "memory": lambda: memory,
    }[request.param]


def test_read_starts_at_the_beginning_and_continues_from_an_offset(new_log):
    log = new_log()
    for name in ("a", "b", "c"):
        log.append(_envelope(name))

    first = log.read("test", 0, 2)
    second = log.read("test", first[-1][1], 10)

    assert _names(first) == ["a", "b"] and _names(second) == ["c"]
    assert log.read("test", second[-1][1], 10) == []
    assert log.read("other", 0, 10) == []


def test_envelopes_are_read_as_they_were_written(new_log):
    log = new_log()
    envelope = _envelope("Zürich 日本")
    log.append(envelope)

    ((read, _),) = log.read("test", 0, 1)

    assert read == envelope


def test_events_offsets_and_dead_letters_survive_a_new_instance(new_log):
    log = new_log()
    log.append(_envelope("a"))
    ((_, offset),) = log.read("test", 0, 1)
    log.commit_offset(GROUP, "test", offset)
    log.commit_offset(GROUP, "test", offset)  # a second time updates
    log.dead_letter(GROUP, _envelope("broken"), "ValueError: no")

    again = new_log()

    assert again.committed_offset(GROUP, "test") == offset
    assert again.committed_offset("another-group", "test") == 0
    assert _names(again.read("test", 0, 10)) == ["a"]
    again.append(_envelope("b"))
    assert _names(again.read("test", offset, 10)) == ["b"]


# ---------------------------------------------------------------- sql


def test_sql_log_gives_gap_free_sequences_to_concurrent_writers(tmp_path: Path):
    """With two writers a later event must not become visible before an earlier one (a consumer would skip it)."""
    log = SqlEventLog(create_engine(f"sqlite:///{tmp_path / 'log.db'}", connect_args={"timeout": 30}))
    log.append(_envelope("first"))  # so the threads don't race to create the topic's row
    errors: list[BaseException] = []

    def write(thread: int) -> None:
        try:
            for i in range(25):
                log.append(_envelope(f"{thread}-{i}"))
        except BaseException as e:
            errors.append(e)

    threads = [threading.Thread(target=write, args=(t,)) for t in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    events = log.read("test", 0, 1000)
    assert errors == []
    assert [offset for _, offset in events] == list(range(1, 102))


def test_sql_log_creates_the_row_of_a_new_topic_once_with_concurrent_writers(tmp_path: Path):
    log = SqlEventLog(create_engine(f"sqlite:///{tmp_path / 'log.db'}", connect_args={"timeout": 30}))
    errors: list[BaseException] = []

    def write() -> None:
        try:
            log.append(_envelope())
        except BaseException as e:
            errors.append(e)

    threads = [threading.Thread(target=write) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []
    assert [offset for _, offset in log.read("test", 0, 100)] == list(range(1, 9))


def test_sql_log_tables_stay_out_of_an_apps_metadata():
    assert not [name for name in SQLModel.metadata.tables if name.startswith("event_log")]


def test_sql_log_tables_compile_for_sql_server():
    compiled = [str(CreateTable(table).compile(dialect=mssql.dialect())) for table in _Model.metadata.sorted_tables]

    assert len(compiled) == 4
    assert all("IDENTITY" not in ddl for ddl in compiled if "event_log_entries" in ddl)
    assert any("NTEXT" in ddl or "NVARCHAR(max)" in ddl for ddl in compiled if "event_log_entries" in ddl)


# ---------------------------------------------------------------- azure_blob


def test_azure_log_continues_in_a_new_segment_and_sealed_the_old_one():
    container = FakeContainer()
    log = AzureBlobEventLog(container, max_blocks=2)

    for name in ("a", "b", "c", "d", "e"):
        log.append(_envelope(name))

    segments = sorted(name for name in container.blobs if name.startswith("topics/"))
    assert segments == [f"topics/test/{n:010d}.jsonl" for n in range(3)]
    assert [container.blobs[name].sealed for name in segments] == [True, True, False]

    events = log.read("test", 0, 3)
    assert _names(events) == ["a", "b", "c"]
    assert _names(log.read("test", events[-1][1], 10)) == ["d", "e"]


def test_azure_log_offsets_only_grow_across_segments():
    log = AzureBlobEventLog(FakeContainer(), max_blocks=2)
    for name in ("a", "b", "c"):
        log.append(_envelope(name))

    offsets = [offset for _, offset in log.read("test", 0, 10)]

    assert offsets == sorted(offsets) and len(set(offsets)) == 3


def test_azure_log_reader_stays_on_a_full_segment_until_it_is_sealed():
    """A second writer may still append to it: moving on before the seal would miss that event."""
    container = FakeContainer()
    log = AzureBlobEventLog(container, max_blocks=100)
    log.append(_envelope("a"))
    ((_, offset),) = log.read("test", 0, 1)
    next_segment = container.get_blob_client(f"topics/test/{1:010d}.jsonl")
    container.blobs[next_segment.name] = type(container.blobs["topics/test/0000000000.jsonl"])(
        data=(_envelope("later").model_dump_json() + "\n").encode(), blocks=1, sealed=False
    )

    assert log.read("test", offset, 10) == []  # not sealed yet

    container.get_blob_client("topics/test/0000000000.jsonl").seal_append_blob()

    assert _names(log.read("test", offset, 10)) == ["later"]


def test_azure_log_writer_moves_on_when_another_instance_sealed_the_segment():
    container = FakeContainer()
    writer = AzureBlobEventLog(container)
    writer.append(_envelope("a"))
    container.get_blob_client("topics/test/0000000000.jsonl").seal_append_blob()

    writer.append(_envelope("b"))

    assert sorted(name for name in container.blobs if name.startswith("topics/")) == [
        "topics/test/0000000000.jsonl",
        "topics/test/0000000001.jsonl",
    ]
    assert _names(writer.read("test", 0, 10)) == ["a", "b"]


def test_azure_log_new_instance_appends_to_the_newest_segment():
    container = FakeContainer()
    first = AzureBlobEventLog(container, max_blocks=1)
    first.append(_envelope("a"))

    second = AzureBlobEventLog(container)
    second.append(_envelope("b"))

    assert _names(second.read("test", 0, 10)) == ["a", "b"]
    assert not container.blobs["topics/test/0000000001.jsonl"].sealed


def test_azure_log_reads_an_event_larger_than_the_first_read(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("commons.events.azure_blob._READ_SIZE", 16)
    log = AzureBlobEventLog(FakeContainer())
    log.append(_envelope("x" * 200))

    assert _names(log.read("test", 0, 1)) == ["x" * 200]


def test_azure_log_rejects_unsafe_names():
    with pytest.raises(ValueError):
        AzureBlobEventLog(FakeContainer()).committed_offset("../escape", "topic")
