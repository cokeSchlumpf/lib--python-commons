from sqlalchemy import create_engine

from commons.users import RegisteredUser, SQLUsersRepository


def _create(repo: SQLUsersRepository, locale: str | None = None) -> RegisteredUser:
    return repo.upsert_user(RegisteredUser.create("jane", None, "Jane Doe", email="jane@example.com", locale=locale))


class TestUserLocale:
    def test_none_by_default(self, tmp_path):
        repo = SQLUsersRepository(create_engine(f"sqlite:///{tmp_path / 'users.db'}"))

        assert _create(repo).locale is None

    def test_is_stored_and_can_be_changed(self, tmp_path):
        repo = SQLUsersRepository(create_engine(f"sqlite:///{tmp_path / 'users.db'}"))
        _create(repo, "de")

        user = repo.get_user_by_username("jane")
        assert user.locale == "de"
        user.locale = "fr"
        repo.upsert_user(user)

        assert repo.get_user_by_username("jane").locale == "fr"

    def test_is_kept_when_the_password_changes(self, tmp_path):
        repo = SQLUsersRepository(create_engine(f"sqlite:///{tmp_path / 'users.db'}"))
        _create(repo, "it")

        repo.update_password("jane", "new-secret")

        assert repo.get_user_by_username("jane").locale == "it"
