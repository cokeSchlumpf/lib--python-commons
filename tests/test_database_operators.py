from unittest.mock import patch

from sqlalchemy.engine import URL

from commons import database_operators
from commons.settings import DatabaseSettings, MSSQLSettings


def _mssql_settings(**overrides) -> DatabaseSettings:
    settings = DatabaseSettings(mode="mssql")
    settings.mssql = MSSQLSettings(
        server="srv.example.com",
        database="db",
        username="u",
        password="p",
        **overrides,
    )
    return settings


def _build_url(settings: DatabaseSettings) -> URL:
    """Run create_engine() with stubbed settings and capture the URL handed to SQLAlchemy."""
    with (
        patch.object(database_operators.settings.DatabaseSettings, "read", return_value=settings),
        patch.object(database_operators, "sql_alchemy_create_engine") as fake_create,
    ):
        database_operators.create_engine()

    assert fake_create.call_count == 1
    url = fake_create.call_args.args[0]
    assert isinstance(url, URL)
    return url


class TestMSSQLDefaults:
    def test_default_port_is_1433(self):
        url = _build_url(_mssql_settings())
        assert url.port == 1433

    def test_default_query_params(self):
        url = _build_url(_mssql_settings())
        assert dict(url.query) == {
            "driver": "ODBC Driver 18 for SQL Server",
            "Encrypt": "yes",
            "TrustServerCertificate": "no",
            "Connection Timeout": "30",
        }

    def test_basic_connection_fields(self):
        url = _build_url(_mssql_settings())
        assert url.drivername == "mssql+pyodbc"
        assert url.host == "srv.example.com"
        assert url.username == "u"
        assert url.password == "p"
        assert url.database == "db"


class TestMSSQLCustomPort:
    def test_custom_port_is_used(self):
        url = _build_url(_mssql_settings(port=1434))
        assert url.port == 1434

    def test_custom_port_does_not_affect_query(self):
        url = _build_url(_mssql_settings(port=1434))
        assert dict(url.query) == {
            "driver": "ODBC Driver 18 for SQL Server",
            "Encrypt": "yes",
            "TrustServerCertificate": "no",
            "Connection Timeout": "30",
        }


class TestMSSQLQueryOverride:
    def test_override_merges_on_top_of_defaults(self):
        url = _build_url(_mssql_settings(query={"Connection Timeout": "60"}))
        assert dict(url.query) == {
            "driver": "ODBC Driver 18 for SQL Server",
            "Encrypt": "yes",
            "TrustServerCertificate": "no",
            "Connection Timeout": "60",
        }

    def test_override_can_add_new_keys(self):
        url = _build_url(_mssql_settings(query={"MARS_Connection": "yes"}))
        assert url.query["MARS_Connection"] == "yes"
        assert url.query["driver"] == "ODBC Driver 18 for SQL Server"

    def test_override_can_replace_driver(self):
        url = _build_url(_mssql_settings(query={"driver": "ODBC Driver 17 for SQL Server"}))
        assert url.query["driver"] == "ODBC Driver 17 for SQL Server"
