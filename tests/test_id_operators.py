import subprocess
import sys
import uuid

import pytest

import commons.database
from commons.id_operators import new_id


def test_new_id_is_a_36_character_uuid7():
    id_ = new_id()

    assert len(id_) == 36
    assert uuid.UUID(id_).version == 7
    assert str(uuid.UUID(id_)) == id_


def test_new_ids_are_unique_and_in_creation_order():
    ids = [new_id() for _ in range(1000)]

    assert len(set(ids)) == len(ids)
    assert ids == sorted(ids)


def test_new_id_is_re_exported_from_database():
    assert commons.database.new_id is new_id


@pytest.mark.parametrize(
    "first, second",
    [("commons.users", "commons.database"), ("commons.database", "commons.users")],
)
def test_users_and_database_import_in_either_order(first, second):
    code = f"import {first}, {second}; from commons.users import AuthenticatedUser; AuthenticatedUser(display_name='x')"

    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)

    assert result.returncode == 0, result.stderr
