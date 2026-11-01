import io

import bcrypt
import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from commons.settings import StandardUser, StandardUserSettings
from commons.users import RegisteredUser, Role, SQLUsersRepository
from commons.users.__main__ import main


def _user(**kwargs) -> dict:
    return {"username": "john.doe", "firstname": "John", "lastname": "Doe", "email": "john@example.com", **kwargs}


@pytest.fixture
def repo() -> SQLUsersRepository:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    return SQLUsersRepository(engine)


def test_standard_user_may_have_neither_password_nor_hash():
    user = StandardUser.model_validate(_user())

    assert user.password is None and user.password_hash is None


def test_standard_user_rejects_password_and_hash():
    with pytest.raises(ValidationError, match="not both"):
        StandardUser.model_validate(_user(password="secret", password_hash="$2b$12$abc"))


def test_init_from_settings_hashes_plain_password(repo):
    repo.init_from_settings(StandardUserSettings.model_validate({"users": [_user(password="secret")]}))

    user = repo.get_user_by_username("john.doe")
    assert user.password_hash != "secret"
    assert repo.authenticate("john.doe", "secret") is not None


def test_init_from_settings_stores_password_hash_as_is(repo):
    password_hash = bcrypt.hashpw(b"secret", bcrypt.gensalt()).decode()

    repo.init_from_settings(StandardUserSettings.model_validate({"users": [_user(password_hash=password_hash)]}))

    assert repo.get_user_by_username("john.doe").password_hash == password_hash
    assert repo.authenticate("john.doe", "secret") is not None
    assert repo.authenticate("john.doe", "wrong") is None


def test_hash_password_cli_from_stdin(monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin", io.StringIO("secret\n"))

    main(["hash-password", "--stdin"])

    password_hash = capsys.readouterr().out.strip()
    assert bcrypt.checkpw(b"secret", password_hash.encode())


def test_hash_password_cli_prompts_twice(monkeypatch, capsys):
    answers = iter(["secret", "secret"])
    monkeypatch.setattr("getpass.getpass", lambda _prompt: next(answers))

    main(["hash-password"])

    assert bcrypt.checkpw(b"secret", capsys.readouterr().out.strip().encode())


def test_hash_password_cli_rejects_mismatch(monkeypatch):
    answers = iter(["secret", "other"])
    monkeypatch.setattr("getpass.getpass", lambda _prompt: next(answers))

    with pytest.raises(SystemExit, match="do not match"):
        main(["hash-password"])


def test_init_from_settings_keeps_existing_users(repo):
    repo.upsert_role(Role.create("viewer", ["/read"]))
    settings = StandardUserSettings.model_validate(
        {"users": [_user(password="secret", roles=[{"role": "viewer", "scope": "/"}])]}
    )
    repo.init_from_settings(settings)
    repo.update_password("john.doe", "changed")

    repo.init_from_settings(settings)

    assert repo.authenticate("john.doe", "changed") is not None
    assert repo.authenticate("john.doe", "secret") is None
    assert len(repo.get_role_assignments("john.doe")) == 1


def test_init_from_settings_creates_user_without_password(repo):
    repo.init_from_settings(StandardUserSettings.model_validate({"users": [_user()]}))

    assert repo.get_user_by_username("john.doe").password_hash is None
    assert repo.authenticate("john.doe", "") is None
    assert repo.authenticate("john.doe", "anything") is None


@pytest.mark.parametrize("password_hash", [None, ""])
def test_authenticate_rejects_user_without_password(repo, password_hash):
    repo.upsert_user(RegisteredUser.create("jane", password_hash, "Jane"))

    assert repo.authenticate("jane", "") is None
    assert repo.authenticate("jane", "secret") is None


def test_hash_password_rejects_empty_password(repo):
    with pytest.raises(ValueError, match="empty"):
        repo.hash_password("")


def test_update_password_rejects_empty_password(repo):
    repo.upsert_user(RegisteredUser.create("jane", repo.hash_password("secret"), "Jane"))

    with pytest.raises(ValueError, match="empty"):
        repo.update_password("jane", "")

    assert repo.authenticate("jane", "secret") is not None


def test_init_from_settings_rejects_empty_plain_password(repo):
    with pytest.raises(ValueError, match="empty"):
        repo.init_from_settings(StandardUserSettings.model_validate({"users": [_user(password="")]}))


def test_hash_password_cli_rejects_empty_password(monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO("\n"))

    with pytest.raises(SystemExit, match="must not be empty"):
        main(["hash-password", "--stdin"])
