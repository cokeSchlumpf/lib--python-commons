from pathlib import Path
from unittest.mock import patch

from commons import storage_operators
from commons.settings import LocalStorageSettings, StorageSettings
from commons.storage import LocalFiles


def _stub_storage(settings: StorageSettings):
    """Patch StorageSettings.read to return the supplied settings."""
    return patch.object(storage_operators.settings.StorageSettings, "read", return_value=settings)


class TestCreateFilesLocal:
    def test_default_mode_returns_local_files_with_default_root(self, tmp_path):
        settings = StorageSettings()  # mode=local, local=None

        # AppSettings.data_dir / "files" is the fallback. Patch AppSettings.read so we
        # don't depend on the working directory.
        from commons.settings import AppSettings

        app_settings = AppSettings(version="test", environment="local", data_dir=str(tmp_path))

        with (
            _stub_storage(settings),
            patch.object(storage_operators.settings.AppSettings, "read", return_value=app_settings),
        ):
            result = storage_operators.create_files()

        assert isinstance(result, LocalFiles)
        assert result._root == tmp_path / "files"

    def test_local_mode_with_explicit_root(self, tmp_path):
        settings = StorageSettings(mode="local", local={"root": str(tmp_path / "custom")})

        with _stub_storage(settings):
            result = storage_operators.create_files()

        assert isinstance(result, LocalFiles)
        assert result._root == tmp_path / "custom"

from commons.storage import SQLFiles
from unittest.mock import MagicMock, patch

class TestCreateFilesSql:
    def test_sql_mode_returns_sql_files(self):
        settings = StorageSettings(mode="sql")

        # Patch the SQL engine creation so we don't need a real DB.
        with (
            _stub_storage(settings),
            patch("commons.storage.sql.create_engine") as fake_create_engine,
        ):
            fake_create_engine.return_value.dialect = MagicMock()
            # SQLFiles will call _FilePE.metadata.create_all on the engine; mock it out.
            with patch("commons.storage.sql._FilePE.metadata.create_all"):
                result = storage_operators.create_files()

        assert isinstance(result, SQLFiles)
        fake_create_engine.assert_called_once()

import pytest

from commons.storage import AzureFiles


class TestCreateFilesAzure:
    def test_azure_mode_without_azure_block_raises(self):
        settings = StorageSettings(mode="azure")  # no azure sub-dict

        with _stub_storage(settings):
            with pytest.raises(AssertionError, match="Azure storage settings"):
                storage_operators.create_files()

    def test_azure_mode_returns_azure_files(self):
        settings = StorageSettings(
            mode="azure",
            azure={
                "auth_mode": "default_credential",
                "account_url": "https://acct.blob.core.windows.net",
                "container": "files",
            },
        )

        # Patch _build_container_client so we don't try to authenticate.
        with (
            _stub_storage(settings),
            patch("commons.storage.azure._build_container_client") as fake_build,
        ):
            fake_build.return_value = MagicMock()
            result = storage_operators.create_files()

        assert isinstance(result, AzureFiles)
        fake_build.assert_called_once()
        # The settings passed to _build_container_client must be the one from StorageSettings.
        passed = fake_build.call_args.args[0]
        assert passed.container == "files"

