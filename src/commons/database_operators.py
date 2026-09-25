"""Database connection and settings operators."""

from pathlib import Path

from commons import settings
from sqlalchemy import Engine, create_engine as sql_alchemy_create_engine
from sqlalchemy.engine import URL


def create_engine() -> Engine:
    database_settings = settings.DatabaseSettings.read()

    if database_settings.mode == "mssql":
        assert database_settings.mssql is not None, "MSSQL database settings must be present, if mode is mssql."

        default_query = {
            "driver": "ODBC Driver 18 for SQL Server",
            "Encrypt": "yes",
            "TrustServerCertificate": "no",
            "Connection Timeout": "30",
        }
        query = {**default_query, **(database_settings.mssql.query or {})}

        url = URL.create(
            "mssql+pyodbc",
            username=database_settings.mssql.username,
            password=database_settings.mssql.password,
            host=database_settings.mssql.server,
            port=database_settings.mssql.port,
            database=database_settings.mssql.database,
            query=query,
        )

        return sql_alchemy_create_engine(url, future=True)

    else:
        app_settings = settings.AppSettings.read()

        if database_settings.local and database_settings.local.path:
            path = Path(database_settings.local.path)
            if path.is_absolute():
                database_file = path
            else:
                database_file = (app_settings.data_dir / path).absolute()
        else:
            database_file = (app_settings.data_dir / "database.db").absolute()

        database_file.parent.mkdir(parents=True, exist_ok=True)

        return sql_alchemy_create_engine(f"sqlite:///{str(database_file)}")
