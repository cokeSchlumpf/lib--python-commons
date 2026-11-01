from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.dialects import mssql, sqlite
from sqlalchemy.schema import CreateTable
from sqlmodel import Field, Session, SQLModel, select

from commons.database import EntityMixin, HistoryMixin, UnicodeCode, UnicodeName
from commons.users import AuthenticatedUser, RegisteredUser

NAME = "Łucja Wąs-Müller Ωμέγα"


class _NoteFields(SQLModel):
    code: str = Field(sa_type=UnicodeCode)
    title: str = Field(sa_type=UnicodeName)
    ascii_key: str = Field(max_length=255)


class UnicodeNoteORM(_NoteFields, EntityMixin, table=True):
    pass


class UnicodeNoteHistoryORM(_NoteFields, HistoryMixin[UnicodeNoteORM], table=True):
    pass


def _ddl(table: object, dialect: object) -> str:
    return str(CreateTable(table).compile(dialect=dialect))  # type: ignore[arg-type]


def test_unicode_types_are_nvarchar_on_sql_server_also_in_a_shared_fields_class() -> None:
    for table in (UnicodeNoteORM.__table__, UnicodeNoteHistoryORM.__table__):  # type: ignore[attr-defined]
        ddl = _ddl(table, mssql.dialect())
        assert "code NVARCHAR(64)" in ddl
        assert "title NVARCHAR(255)" in ddl
        assert "ascii_key VARCHAR(255)" in ddl


def test_unicode_types_are_varchar_on_sqlite() -> None:
    ddl = _ddl(UnicodeNoteORM.__table__, sqlite.dialect())  # type: ignore[attr-defined]

    assert "code VARCHAR(64)" in ddl and "title VARCHAR(255)" in ddl


def test_the_display_name_in_the_history_is_nvarchar_and_the_user_id_varchar() -> None:
    ddl = _ddl(UnicodeNoteHistoryORM.__table__, mssql.dialect())  # type: ignore[attr-defined]

    assert "history_changed_by_user_displayname NVARCHAR(255)" in ddl
    assert "history_changed_by_user_id VARCHAR(255)" in ddl


def test_the_names_of_registered_users_are_nvarchar_and_the_other_columns_unchanged() -> None:
    ddl = _ddl(RegisteredUser.__table__, mssql.dialect())  # type: ignore[attr-defined]

    for column in ["display_name NVARCHAR(128)", "firstname NVARCHAR(64)", "lastname NVARCHAR(64)"]:
        assert column in ddl
    for column in ["id VARCHAR(64)", "username VARCHAR(64)", "email VARCHAR(128)", "locale VARCHAR(35)"]:
        assert column in ddl


def test_names_round_trip_unchanged(tmp_path: Path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        note = UnicodeNoteORM(code="IV-ł", title=NAME, ascii_key="k")
        session.add(note)
        UnicodeNoteHistoryORM.record(session, AuthenticatedUser.create(NAME), note)
        user = RegisteredUser.model_validate(
            {"username": "lwas", "display_name": NAME, "firstname": "Łucja", "lastname": "Wąs-Müller"}
        )
        session.add(user)
        session.commit()
        note_id, user_id = note.id, user.id

    with Session(engine) as session:
        stored = session.get(UnicodeNoteORM, note_id)
        assert stored is not None and (stored.code, stored.title) == ("IV-ł", NAME)
        (version,) = session.exec(select(UnicodeNoteHistoryORM)).all()
        assert version.history_changed_by_user_displayname == NAME
        stored_user = session.get(RegisteredUser, user_id)
        assert stored_user is not None
        assert (stored_user.display_name, stored_user.firstname, stored_user.lastname) == (NAME, "Łucja", "Wąs-Müller")
