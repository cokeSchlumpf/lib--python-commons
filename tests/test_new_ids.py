"""The ids `commons` generates for new objects are UUIDv7 (`commons.id_operators.new_id`); explicit ids are kept."""

import uuid
from typing import ClassVar

from sqlalchemy import create_engine
from sqlmodel import SQLModel

from commons.database import EntityMixin
from commons.events import Event
from commons.users import AuthenticatedUser, RegisteredUser
from commons.users.user import RoleAssignment
from jobs.sql import SQLJobsRepository

EXPLICIT_ID = "11111111-1111-1111-1111-111111111111"


class ThingORM(EntityMixin, SQLModel, table=True):
    name: str = ""


class _Happened(Event):
    topic: ClassVar[str] = "test"
    event_type: ClassVar[str] = "happened"


def _is_uuid7(id_: str) -> bool:
    return len(id_) == 36 and uuid.UUID(id_).version == 7


def test_entities_get_uuid7_ids():
    assert _is_uuid7(ThingORM().id)
    assert ThingORM(id=EXPLICIT_ID).id == EXPLICIT_ID


def test_authenticated_users_get_uuid7_ids():
    assert _is_uuid7(AuthenticatedUser(display_name="Jane").id)
    assert _is_uuid7(AuthenticatedUser.create("Jane").id)
    assert AuthenticatedUser.create("Jane", id=EXPLICIT_ID).id == EXPLICIT_ID


def test_registered_users_get_uuid7_ids():
    assert _is_uuid7(RegisteredUser(username="jane", password_hash="x", display_name="Jane").id)
    assert _is_uuid7(RegisteredUser.create("jane", "x", "Jane").id)
    assert RegisteredUser.create("jane", "x", "Jane", id=EXPLICIT_ID).id == EXPLICIT_ID


def test_role_assignments_get_uuid7_ids():
    assignment = RoleAssignment(scope_name="/", role_name="admin", user_id=EXPLICIT_ID)

    assert _is_uuid7(assignment.id)


def test_jobs_get_uuid7_ids(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'jobs.db'}")
    repo = SQLJobsRepository(engine)
    try:
        assert _is_uuid7(repo.create(file=tmp_path / "job.py").id)
        assert repo.create(file=tmp_path / "job.py", id=EXPLICIT_ID).id == EXPLICIT_ID
    finally:
        engine.dispose()


def test_events_get_uuid7_ids():
    assert _is_uuid7(_Happened().event_id)
    assert _Happened(event_id=EXPLICIT_ID).event_id == EXPLICIT_ID
