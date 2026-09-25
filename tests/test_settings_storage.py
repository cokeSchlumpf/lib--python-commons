import logging
from pathlib import Path
from unittest.mock import patch

from commons.settings import AzureStorageSettings
from commons.settings import LocalStorageSettings
from commons.settings import StorageSettings

#Testing LocalStorageSettings
class TestLocalStorageSettings:
    def test_defaults_to_none_root(self):
        settings = LocalStorageSettings()
        assert settings.root is None

    def test_accepts_explicit_root(self):
        settings = LocalStorageSettings(root="/var/data/files")
        assert settings.root == "/var/data/files"


#Testing AzureStorageSettings
class TestAzureStorageSettingsDefaults:
    def test_default_auth_mode(self):
        settings = AzureStorageSettings()
        assert settings.auth_mode == "default_credential"

    def test_default_string_fields_are_empty(self):
        settings = AzureStorageSettings()
        assert settings.account_url == ""
        assert settings.container == ""
        assert settings.account_name == ""

    def test_ignores_extra_kwargs(self):
        # Forward-compat: unknown TOML keys must not raise.
        AzureStorageSettings(unknown_field="whatever")


class TestAzureStorageSettingsConnectionString:
    def test_returns_configured_value(self, caplog):
        settings = AzureStorageSettings(
            auth_mode="connection_string", connection_string="DefaultEndpointsProtocol=https;..."
        )
        with caplog.at_level(logging.WARNING):
            assert settings.connection_string == "DefaultEndpointsProtocol=https;..."
        assert caplog.records == []

    def test_warns_when_missing(self, caplog):
        settings = AzureStorageSettings(auth_mode="connection_string", connection_string="")
        with caplog.at_level(logging.WARNING):
            value = settings.connection_string
        assert value == ""
        assert any("connection_string" in r.message for r in caplog.records)

    def test_warns_when_placeholder(self, caplog):
        settings = AzureStorageSettings(auth_mode="connection_string", connection_string="xxx")
        with caplog.at_level(logging.WARNING):
            settings.connection_string
        assert any("connection_string" in r.message for r in caplog.records)

    def test_does_not_warn_when_auth_mode_is_different(self, caplog):
        settings = AzureStorageSettings(auth_mode="default_credential", connection_string="")
        with caplog.at_level(logging.WARNING):
            settings.connection_string
        assert caplog.records == []


class TestAzureStorageSettingsAccountKey:
    def test_returns_configured_value(self, caplog):
        settings = AzureStorageSettings(
            auth_mode="account_key", account_name="acct", account_key="abc123"
        )
        with caplog.at_level(logging.WARNING):
            assert settings.account_key == "abc123"
        assert caplog.records == []

    def test_warns_when_missing(self, caplog):
        settings = AzureStorageSettings(auth_mode="account_key", account_name="acct", account_key="")
        with caplog.at_level(logging.WARNING):
            value = settings.account_key
        assert value == ""
        assert any("account_key" in r.message for r in caplog.records)

    def test_warns_when_placeholder(self, caplog):
        settings = AzureStorageSettings(auth_mode="account_key", account_name="acct", account_key="xxx")
        with caplog.at_level(logging.WARNING):
            settings.account_key
        assert any("account_key" in r.message for r in caplog.records)

    def test_does_not_warn_when_auth_mode_is_different(self, caplog):
        settings = AzureStorageSettings(auth_mode="default_credential", account_key="")
        with caplog.at_level(logging.WARNING):
            settings.account_key
        assert caplog.records == []


#Testing StorageSettings
class TestStorageSettings:
    def test_default_mode_is_local(self):
        settings = StorageSettings()
        assert settings.mode == "local"
        assert settings.local is None
        assert settings.azure is None

    def test_local_mode_with_local_block(self):
        settings = StorageSettings(mode="local", local={"root": "/var/data/files"})
        assert settings.mode == "local"
        assert isinstance(settings.local, LocalStorageSettings)
        assert settings.local.root == "/var/data/files"
        assert settings.azure is None

    def test_azure_mode_with_azure_block(self):
        settings = StorageSettings(
            mode="azure",
            azure={"auth_mode": "default_credential", "account_url": "https://x.blob.core.windows.net", "container": "files"},
        )
        assert settings.mode == "azure"
        assert settings.local is None
        assert isinstance(settings.azure, AzureStorageSettings)
        assert settings.azure.account_url == "https://x.blob.core.windows.net"
        assert settings.azure.container == "files"

    def test_sql_mode_has_no_subblock(self):
        # SQL mode reuses DatabaseSettings; StorageSettings holds no sql-specific fields.
        settings = StorageSettings(mode="sql")
        assert settings.mode == "sql"
        assert settings.local is None
        assert settings.azure is None


#Integration Testing
class TestStorageSettingsFromToml:
    def test_reads_azure_section_from_settings_toml(self, tmp_path, clean_app_env):
        settings_file = tmp_path / "settings.toml"
        settings_file.write_text(
            "[app.storage]\n"
            'mode = "azure"\n'
            "\n"
            "[app.storage.azure]\n"
            'auth_mode = "default_credential"\n'
            'account_url = "https://acct.blob.core.windows.net"\n'
            'container = "files"\n'
        )

        with patch("commons.path_operators.get_project_root_dir", return_value=tmp_path):
            with patch.object(Path, "home", return_value=tmp_path / "nonexistent_home"):
                result = StorageSettings.read()

        assert result.mode == "azure"
        assert result.azure is not None
        assert result.azure.account_url == "https://acct.blob.core.windows.net"
        assert result.azure.container == "files"
