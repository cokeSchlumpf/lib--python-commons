"""`UTCDateTime` keeps microseconds on every engine, as it is part of history tables' keys."""

from datetime import datetime, timezone

from sqlalchemy import Column, Integer, MetaData, Table, create_engine, select
from sqlalchemy.dialects import mssql, sqlite
from sqlalchemy.schema import CreateTable

from commons.database import UTCDateTime

_TABLE = Table("t", MetaData(), Column("id", Integer, primary_key=True), Column("at", UTCDateTime))


def test_it_is_datetime2_on_sql_server():
    assert "at DATETIME2" in str(CreateTable(_TABLE).compile(dialect=mssql.dialect())).replace("[", "").replace("]", "")


def test_it_stays_datetime_on_sqlite():
    assert "at DATETIME" in str(CreateTable(_TABLE).compile(dialect=sqlite.dialect()))
    assert "DATETIME2" not in str(CreateTable(_TABLE).compile(dialect=sqlite.dialect()))


def test_microseconds_survive_on_sqlite():
    engine = create_engine("sqlite://")
    _TABLE.metadata.create_all(engine)
    value = datetime(2026, 11, 7, 12, 0, 0, 123456, tzinfo=timezone.utc)

    with engine.begin() as connection:
        connection.execute(_TABLE.insert().values(id=1, at=value))
        read = connection.execute(select(_TABLE.c.at)).scalar()

    assert read == value.replace(tzinfo=None)
