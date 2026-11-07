"""`EventsSettings` from ``[app.events]`` and `background_workers_from_settings`."""

from dataclasses import dataclass
from datetime import timedelta

import pytest
from pydantic import ValidationError
from sqlalchemy.orm import sessionmaker
from sqlmodel import Session, create_engine

from commons.database import SqlUnitOfWorkFactory
from commons.settings import AzureStorageSettings
from commons.events.settings import _event_log

from tests.fake_blob_container import FakeContainer

from commons.events import (
    AzureBlobEventLog,
    SqlEventLog,
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


def test_the_durable_modes_have_their_settings():
    settings = EventsSettings(mode="sql", sql={"pool_size": 5}, azure_blob={"container": "app-events"})

    assert settings.sql.pool_size == 5 and settings.azure_blob.container == "app-events"
    assert EventsSettings().mode == "file"
    assert EventsSettings().sql.pool_size == 2 and EventsSettings().azure_blob.container == "events"


def test_sql_mode_builds_the_log_on_an_engine_of_its_own(monkeypatch: pytest.MonkeyPatch):
    calls: list[dict] = []

    def engine(**options):
        calls.append(options)
        return create_engine("sqlite://")

    monkeypatch.setattr("commons.database_operators.create_engine", engine)

    log = _event_log(EventsSettings(mode="sql", sql={"pool_size": 3}))

    assert isinstance(log, SqlEventLog)
    assert calls == [{"pool_size": 3, "pool_pre_ping": True}]


def test_azure_blob_mode_uses_the_account_of_the_storage_and_its_own_container(monkeypatch: pytest.MonkeyPatch):
    seen: list[str | None] = []

    def client(settings, container=None):
        seen.append(container)
        return FakeContainer()

    monkeypatch.setattr("commons.storage.azure._build_container_client", client)
    monkeypatch.setattr(AzureStorageSettings, "read", staticmethod(lambda: AzureStorageSettings(container="appdata")))

    log = _event_log(EventsSettings(mode="azure_blob"))

    assert isinstance(log, AzureBlobEventLog)
    assert seen == ["events"]
