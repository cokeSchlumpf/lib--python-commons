import sqlite3

from sqlalchemy import create_engine, inspect
from sqlalchemy.dialects import mssql, sqlite

from commons.users import RegisteredUser, SQLUsersRepository
from commons.users.sql import _add_users_locale_statement


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


# The table as commons 1.3.0 created it (without `locale`).
_TABLE_1_3 = """
CREATE TABLE registered_users (
    id VARCHAR(64) NOT NULL PRIMARY KEY,
    username VARCHAR(64) UNIQUE,
    password_hash VARCHAR(256),
    display_name VARCHAR(128),
    firstname VARCHAR(64),
    lastname VARCHAR(64),
    email VARCHAR(128)
)
"""


class TestMigration:
    def test_adds_the_column_to_an_existing_table_and_keeps_its_rows(self, tmp_path):
        path = tmp_path / "users.db"
        with sqlite3.connect(path) as connection:
            connection.execute(_TABLE_1_3)
            connection.execute(
                "INSERT INTO registered_users VALUES ('u1', 'jane', NULL, 'Jane Doe', 'Jane', 'Doe', 'jane@example.com')"
            )
        engine = create_engine(f"sqlite:///{path}")

        repo = SQLUsersRepository(engine)

        assert "locale" in {column["name"] for column in inspect(engine).get_columns("registered_users")}
        user = repo.get_user_by_username("jane")
        assert (user.id, user.display_name, user.email, user.locale) == ("u1", "Jane Doe", "jane@example.com", None)

    def test_runs_again_without_changes(self, tmp_path):
        engine = create_engine(f"sqlite:///{tmp_path / 'users.db'}")
        repo = SQLUsersRepository(engine)
        _create(repo, "de")

        SQLUsersRepository(engine)
        SQLUsersRepository(engine)

        assert SQLUsersRepository(engine).get_user_by_username("jane").locale == "de"

    def test_statement_for_sqlite_and_azure_sql(self):
        expected = "ALTER TABLE registered_users ADD locale VARCHAR(35) NULL"

        assert _add_users_locale_statement(sqlite.dialect()) == expected
        assert _add_users_locale_statement(mssql.dialect()) == expected
