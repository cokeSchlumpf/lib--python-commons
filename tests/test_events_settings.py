"""`EventsSettings` from ``[app.events]`` and `background_workers_from_settings`."""

from dataclasses import dataclass
from datetime import timedelta

import pytest
from pydantic import ValidationError
from sqlalchemy.orm import sessionmaker
from sqlmodel import Session, create_engine

from commons.database import SqlUnitOfWorkFactory
from commons.events import (
    CommitNotifyingUnitOfWorkFactory,
    EventsSettings,
    FileEventLog,
    InMemoryEventLog,
    Outbox,
    SqlOutbox,
    background_workers_from_settings,
)


@dataclass
class _Repositories:
    outbox: Outbox


def _factory() -> SqlUnitOfWorkFactory[_Repositories]:
    engine = create_engine("sqlite://")
    return SqlUnitOfWorkFactory(sessionmaker(bind=engine, class_=Session), lambda s, u: _Repositories(SqlOutbox(s)))


def test_defaults_without_section(clean_app_env):
    assert EventsSettings.read() == EventsSettings()
    assert EventsSettings().mode == "file"
    assert EventsSettings().outbox_retention == timedelta(days=7)


def test_values_are_read_from_app_events(clean_app_env, monkeypatch):
    monkeypatch.setenv("APP__EVENTS__MODE", "memory")
    monkeypatch.setenv("APP__EVENTS__HANDLER_MAX_ATTEMPTS", "5")

    settings = EventsSettings.read()

    assert (settings.mode, settings.handler_max_attempts) == ("memory", 5)


def test_unknown_keys_are_rejected(clean_app_env, monkeypatch):
    monkeypatch.setenv("APP__EVENTS__POLL_INTERVAL", "1")

    with pytest.raises(ValidationError):
        EventsSettings.read()


def test_the_file_log_lives_in_the_configured_directory(tmp_path):
    workers = background_workers_from_settings(_factory(), EventsSettings(mode="file", dir=tmp_path))

    log = workers._consumer._log  # type: ignore[attr-defined]
    assert isinstance(log, FileEventLog)
    assert log.root == tmp_path


def test_memory_mode_uses_the_in_memory_log():
    workers = background_workers_from_settings(_factory(), EventsSettings(mode="memory"))

    assert isinstance(workers._consumer._log, InMemoryEventLog)  # type: ignore[attr-defined]


def test_the_relay_is_woken_by_commits_of_a_notifying_factory():
    repositories = CommitNotifyingUnitOfWorkFactory(_factory())

    workers = background_workers_from_settings(repositories, EventsSettings(mode="memory"))

    assert repositories._listeners == [workers._relay.wake]
