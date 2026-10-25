import pytest
from sqlalchemy import create_engine

from commons.users import RegisteredUser, SQLUsersRepository


@pytest.fixture
def repo(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'users.db'}")
    yield SQLUsersRepository(engine)
    engine.dispose()


def _create_user(repo: SQLUsersRepository, username: str, email: str | None) -> RegisteredUser:
    return repo.upsert_user(
        RegisteredUser.create(
            username=username,
            password_hash=repo.hash_password("secret"),
            display_name=username,
            email=email,
        )
    )


class TestFindUserByEmail:
    def test_returns_matching_user(self, repo):
        user = _create_user(repo, "john", "john@example.com")
        _create_user(repo, "jane", "jane@example.com")

        found = repo.find_user_by_email("john@example.com")

        assert found is not None
        assert found.id == user.id
        assert found.username == "john"

    def test_is_case_insensitive(self, repo):
        user = _create_user(repo, "john", "John.Doe@Example.com")

        found = repo.find_user_by_email("john.doe@EXAMPLE.COM")

        assert found is not None
        assert found.id == user.id

    def test_returns_none_if_not_found(self, repo):
        _create_user(repo, "john", "john@example.com")

        assert repo.find_user_by_email("unknown@example.com") is None

    def test_ignores_users_without_email(self, repo):
        _create_user(repo, "john", None)

        assert repo.find_user_by_email("john@example.com") is None

    def test_raises_if_email_is_ambiguous(self, repo):
        _create_user(repo, "john", "shared@example.com")
        _create_user(repo, "jane", "SHARED@example.com")

        with pytest.raises(ValueError, match="Multiple users"):
            repo.find_user_by_email("shared@example.com")


class TestGetUserByEmail:
    def test_returns_matching_user(self, repo):
        user = _create_user(repo, "john", "john@example.com")

        assert repo.get_user_by_email("john@example.com").id == user.id

    def test_raises_if_not_found(self, repo):
        with pytest.raises(KeyError, match="unknown@example.com"):
            repo.get_user_by_email("unknown@example.com")
