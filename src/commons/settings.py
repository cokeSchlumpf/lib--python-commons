import ast
import logging
import os
import subprocess
import tomllib

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal, Optional, Type, TypeVar

from pydantic import BaseModel, ConfigDict, Field

from commons import dict_operators as dicts
from commons import path_operators


T = TypeVar("T")


LOG = logging.getLogger(__name__)


@dataclass
class AppSettings:
    """Common app settings."""

    version: str

    environment: str

    data_dir: Path

    def __init__(self, version: str = "", environment: str = "", data_dir: str = "", **_kwargs) -> None:
        self.version = version
        self.environment = environment

        if not self.version:
            self.version = _get_git_commit_ref() or "<no version>"

        if not self.environment:
            self.environment = "local"

        if not data_dir:
            self.data_dir = (path_operators.get_project_root_dir() / ".app_data").absolute()
        else:
            self.data_dir = Path(data_dir)

    @staticmethod
    def read() -> "AppSettings":
        return read_settings_object("", AppSettings)


@dataclass
class OpenAISettings:
    """Common settings class for OpenAI settings."""

    model: str = "gpt-5-mini"
    embedding_model: str = "text-embedding-3-small"

    def __init__(
        self, api_key: str = "", model: str = "gpt-5-mini", embedding_model: str = "text-embedding-3-small", **_kwargs
    ) -> None:
        self._api_key = api_key
        self.model = model
        self.embedding_model = embedding_model

    @property
    def api_key(self) -> str:
        if len(self._api_key) == 0 or self._api_key == "xxx":
            user_home = Path.home() / ".wellner" / "settings.toml"

            LOG.warning(
                "No OpenAI Key has been defined in settings, but key is accessed. "
                f"Configure OpenAI settings in `pyproject.toml`, `settings.secrets.toml` or `{user_home.as_posix()}`:\n\n"
                "   [app.models.openai]\n"
                '   api_key = "xxx"\n'
                '   model = "gpt-5-mini"\n'
                '   embedding_model = "text-embedding-3-small"'
            )

        return self._api_key

    @staticmethod
    def read() -> "OpenAISettings":
        return read_settings_object("models.openai", OpenAISettings)


@dataclass
class AzureOpenAISettings:
    """Common settings class for native Azure OpenAI settings."""

    azure_deployment: str = "gpt-4o-mini"
    azure_endpoint: str = ""
    api_version: str = "2025-01-01-preview"
    # Deprecated: use AzureOpenAIEmbeddingSettings instead. Kept for backwards compatibility.
    embedding_model: str = "text-embedding-3-small"

    def __init__(
        self,
        api_key: str = "",
        azure_deployment: str = "gpt-4o-mini",
        azure_endpoint: str = "",
        api_version: str = "2025-01-01-preview",
        embedding_model: str = "text-embedding-3-small",
        **_kwargs,
    ) -> None:
        self._api_key = api_key
        self.azure_deployment = azure_deployment
        self.azure_endpoint = azure_endpoint
        self.api_version = api_version
        # Deprecated: use AzureOpenAIEmbeddingSettings instead. Kept for backwards compatibility.
        self.embedding_model = embedding_model

    @property
    def api_key(self) -> str:
        if len(self._api_key) == 0 or self._api_key == "xxx":
            user_home = Path.home() / ".wellner" / "settings.toml"

            LOG.warning(
                "No Azure OpenAI key has been defined in settings, but key is accessed. "
                f"Configure Azure OpenAI settings in `pyproject.toml`, `settings.secrets.toml` or `{user_home.as_posix()}`:\n\n"
                "   [app.models.azure_openai]\n"
                '   api_key = "xxx"\n'
                '   azure_deployment = "gpt-4o"\n'
                '   azure_endpoint = "https://my-resource.openai.azure.com/"\n'
                '   api_version = "2024-02-01"\n'
                '   embedding_model = "text-embedding-3-small"  # Deprecated: use [app.models.embeddings.azure_openai] instead'
            )

        return self._api_key

    @staticmethod
    def read() -> "AzureOpenAISettings":
        return read_settings_object("models.azure_openai", AzureOpenAISettings)


@dataclass
class AzureOpenAIEmbeddingSettings:
    """Settings class for Azure OpenAI embedding models."""

    azure_deployment: str = "text-embedding-3-small"
    azure_endpoint: str = ""
    api_version: str = "2023-05-15"

    def __init__(
        self,
        api_key: str = "",
        azure_deployment: str = "text-embedding-3-small",
        azure_endpoint: str = "",
        api_version: str = "2023-05-15",
        **_kwargs,
    ) -> None:
        self._api_key = api_key
        self.azure_deployment = azure_deployment
        self.azure_endpoint = azure_endpoint
        self.api_version = api_version

    @property
    def api_key(self) -> str:
        if not self._api_key or self._api_key == "xxx":
            fallback = AzureOpenAISettings.read()
            if fallback.api_key and fallback.api_key != "xxx":
                return fallback.api_key

            user_home = Path.home() / ".wellner" / "settings.toml"

            LOG.warning(
                "No Azure OpenAI embedding key has been defined in settings, but key is accessed. "
                f"Configure Azure OpenAI embedding settings in `pyproject.toml`, `settings.secrets.toml` or `{user_home.as_posix()}`:\n\n"
                "   [app.models.embeddings.azure_openai]\n"
                '   api_key = "xxx"\n'
                '   azure_deployment = "text-embedding-3-small"\n'
                '   azure_endpoint = "https://my-resource.openai.azure.com/"\n'
                '   api_version = "2023-05-15"'
            )

        return self._api_key

    @staticmethod
    def read() -> "AzureOpenAIEmbeddingSettings":
        return read_settings_object("models.embeddings.azure_openai", AzureOpenAIEmbeddingSettings)


@dataclass
class MSSQLSettings:
    """MSSQL database connection settings.

    Attributes:
        server: The FQN of the database server.
        database: The name of the database to access.
        username: The username used to access the database.
        password: The password to access the database.
        port: TCP port of the database server. Defaults to 1433.
        query: Optional overrides for the ODBC connection-string query parameters
            (driver, Encrypt, TrustServerCertificate, Connection Timeout, ...).
            Values provided here are merged on top of the built-in defaults, so
            only keys that need to change must be listed.
    """

    server: str = ""
    database: str = ""
    username: str = ""
    password: str = ""
    port: int = 1433
    query: dict[str, str] | None = None


@dataclass
class LocalDatabaseSettings:
    """Local SQLite database settings.

    Attributes:
        path: The file path for the local SQLite database file.
    """

    path: str | None = None


@dataclass
class DatabaseSettings:
    """Database configuration settings.

    Attributes:
        mode: The database mode for the application.
            - `local`: Will instantiate a local SQLite database. The database file path can be
              configured via `local.path`. If the path is relative, it is resolved against
              `AppSettings.data_dir`. Defaults to `.app_data/database.db` when not configured.
            - `mssql`: Will use mssql settings to connect to a MSSQL database instance.
        local: Local SQLite database settings (optional, used when mode is `local`).
        mssql: MSSQL connection settings (required when mode is `mssql`).
    """

    mode: Literal["local", "mssql"] = "local"
    local: LocalDatabaseSettings | None = None
    mssql: MSSQLSettings | None = None

    def __init__(
        self,
        mode: Literal["local", "mssql"] = "local",
        local: dict[str, Any] | None = None,
        mssql: dict[str, Any] | None = None,
    ) -> None:
        self.mode = mode
        self.local = LocalDatabaseSettings(**local) if local else None
        self.mssql = MSSQLSettings(**mssql) if mssql else None

    @staticmethod
    def read() -> "DatabaseSettings":
        """Read database settings from configuration."""
        return read_settings_object("database", DatabaseSettings)


@dataclass
class LocalStorageSettings:
    """Local filesystem storage settings.

    Attributes:
        root: The root directory for the local file store. If None, falls back to
            ``AppSettings.data_dir / "files"``.
    """

    root: str | None = None

    def __init__(self, root: str | None = None, **_kwargs):
        self.root = root


@dataclass
class AzureStorageSettings:
    """Azure Blob Storage settings.

    Attributes:
        auth_mode: Authentication mode for connecting to Azure Storage.
            - ``default_credential``: Use ``azure.identity.DefaultAzureCredential``
              (managed identity, az login, env vars). Requires ``account_url``.
            - ``connection_string``: Authenticate via a full connection string.
            - ``account_key``: Authenticate via account name + account key. Requires
              ``account_name`` and ``account_key`` (and optionally ``account_url``).
        account_url: Blob service endpoint, e.g.
            ``https://myaccount.blob.core.windows.net``.
        container: Name of the blob container that backs this Files instance.
        account_name: Storage account name (used with ``account_key`` auth).
    """

    auth_mode: Literal["default_credential", "connection_string", "account_key"] = "default_credential"
    account_url: str = ""
    container: str = ""
    account_name: str = ""

    def __init__(
        self,
        auth_mode: Literal["default_credential", "connection_string", "account_key"] = "default_credential",
        account_url: str = "",
        container: str = "",
        connection_string: str = "",
        account_name: str = "",
        account_key: str = "",
        **_kwargs,
    ) -> None:
        self.auth_mode = auth_mode
        self.account_url = account_url
        self.container = container
        self.account_name = account_name
        self._connection_string = connection_string
        self._account_key = account_key

    @property
    def connection_string(self) -> str:
        if self.auth_mode == "connection_string" and (not self._connection_string or self._connection_string == "xxx"):
            user_home = Path.home() / ".wellner" / "settings.toml"
            LOG.warning(
                "No Azure Storage connection_string has been defined in settings, but it is accessed. "
                f"Configure Azure Storage settings in `pyproject.toml`, `settings.secrets.toml` or `{user_home.as_posix()}`:\n\n"
                "   [app.storage.azure]\n"
                '   auth_mode = "connection_string"\n'
                '   container = "files"\n'
                '   connection_string = "xxx"'
            )
        return self._connection_string

    @property
    def account_key(self) -> str:
        if self.auth_mode == "account_key" and (not self._account_key or self._account_key == "xxx"):
            user_home = Path.home() / ".wellner" / "settings.toml"
            LOG.warning(
                "No Azure Storage account_key has been defined in settings, but it is accessed. "
                f"Configure Azure Storage settings in `pyproject.toml`, `settings.secrets.toml` or `{user_home.as_posix()}`:\n\n"
                "   [app.storage.azure]\n"
                '   auth_mode = "account_key"\n'
                '   account_name = "myaccount"\n'
                '   account_key = "xxx"\n'
                '   container = "files"'
            )
        return self._account_key

    @staticmethod
    def read() -> "AzureStorageSettings":
        return read_settings_object("storage.azure", AzureStorageSettings)


@dataclass
class StorageSettings:
    """Storage configuration settings.
    Unknown configuration keys are ignored for forward compatibility.

    Attributes:
        mode: The storage backend for the application.
            - ``local``: Use ``LocalFiles`` rooted at ``local.root`` (or
              ``AppSettings.data_dir / "files"`` if not set).
            - ``sql``: Use ``SQLFiles`` against the engine produced by
              ``DatabaseSettings``. No ``StorageSettings``-level config is needed.
            - ``azure``: Use ``AzureFiles`` configured by ``azure``.
        local: Local filesystem settings (optional, used when mode is ``local``).
        azure: Azure Blob Storage settings (required when mode is ``azure``).
    """

    mode: Literal["local", "sql", "azure"] = "local"
    local: LocalStorageSettings | None = None
    azure: AzureStorageSettings | None = None

    def __init__(
        self,
        mode: Literal["local", "sql", "azure"] = "local",
        local: dict[str, Any] | LocalStorageSettings | None = None,
        azure: dict[str, Any] | AzureStorageSettings | None = None,
        **_kwargs: Any,
    ) -> None:
        self.mode = mode

        if isinstance(local, dict):
            self.local = LocalStorageSettings(**local)
        else:
            self.local = local

        if isinstance(azure, dict):
            self.azure = AzureStorageSettings(**azure)
        else:
            self.azure = azure

    @staticmethod
    def read() -> "StorageSettings":
        return read_settings_object("storage", StorageSettings)


class RoleAssignmentConfig(BaseModel):
    """Configuration for a role assignment.

    Defines which role is assigned to a user within a specific scope.
    """

    role: str = Field(description="The name of the role to assign.")
    scope: str = Field(description="The scope path where the role applies (e.g., '/projects/my-project').")


class StandardUser(BaseModel):
    """A user defined in settings configuration.

    Used for bootstrapping users from configuration files (e.g., settings.toml).
    """

    username: str = Field(description="Unique username for authentication.")
    firstname: str = Field(description="User's first name.")
    lastname: str = Field(description="User's last name.")
    email: str = Field(description="User's email address.")
    password: str = Field(description="Plain-text password (will be hashed when creating the user).")
    roles: list[RoleAssignmentConfig] = Field(
        default_factory=list, description="List of role names to assign to the user."
    )


class StandardUserSettings(BaseModel):
    """Settings container for user definitions.

    Reads user configuration from settings files and provides a list of users
    to be created or synchronized with the user repository.
    """

    model_config = ConfigDict(extra="ignore")

    users: list[StandardUser] = Field(default_factory=list, description="List of users defined in configuration.")

    @staticmethod
    def read() -> "StandardUserSettings":
        """Read users settings from configuration."""
        return read_settings_object("", StandardUserSettings)


@lru_cache
def read_settings(user_home_settings_dir: str = ".wellner", user_home_settings_file: str = "settings.toml") -> dict:
    root_dir = path_operators.get_project_root_dir()
    environment = os.environ.get("APP__ENVIRONMENT", "local")
    user_home = Path.home()

    paths = [
        root_dir / "pyproject.toml",
        root_dir / "settings.toml",
        root_dir / f"settings.{environment}.toml",
        root_dir / ".secrets.toml",
        root_dir / "settings.secrets.toml",
        user_home / user_home_settings_dir / user_home_settings_file,
    ]

    result: dict = {}

    for path in paths:
        result = dicts.deep_merge(result, _read_toml(path))

    result = _merge_env_vars(result)

    return result


def read_settings_object(
    key: str,
    model_cls: Type[T],
    user_home_settings_dir: str = ".wellner",
    user_home_settings_file: str = "settings.toml",
) -> T:
    """Read a nested settings dict and transform it into an object.

    Args:
        key: Dot-separated path to the config section (e.g., "vectorstore.chroma")
        model_cls: Class to instantiate. If it has a `model_validate` method (Pydantic),
                   that will be used. Otherwise, the dict is unpacked as **kwargs.
        user_home_settings_dir: Directory name in user home for settings
        user_home_settings_file: Settings filename in user home directory

    Returns:
        Instance of model_cls populated with the config values

    Raises:
        KeyError: If the key path doesn't exist in settings
    """
    settings = read_settings(user_home_settings_dir, user_home_settings_file)

    data = _get_nested(settings, key)

    if hasattr(model_cls, "model_validate"):
        return model_cls.model_validate(data)  # type: ignore[attr-defined]

    return model_cls(**data)


def _get_git_commit_ref() -> Optional[str]:
    """Return git ref string with commit hash and branch/tag info.

    Returns formats like:
        - "abc1234 (main)" - on a branch
        - "abc1234 (v1.2.3)" - on a tag
        - "abc1234 (HEAD)" - detached HEAD without tag
        - None - not a git repo or git not installed
    """
    try:
        # Get short commit hash
        commit_result = subprocess.run(
            ["git", "rev-parse", "--short=8", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
        commit_hash = commit_result.stdout.strip()

        # Try to get current branch name
        branch_result = subprocess.run(
            ["git", "symbolic-ref", "--short", "HEAD"],
            capture_output=True,
            text=True,
        )

        if branch_result.returncode == 0:
            branch = branch_result.stdout.strip()
            return f"{branch} ({commit_hash})"

        # Not on a branch (detached HEAD) - try to get tag
        tag_result = subprocess.run(
            ["git", "describe", "--tags", "--exact-match", "HEAD"],
            capture_output=True,
            text=True,
        )

        if tag_result.returncode == 0:
            tag = tag_result.stdout.strip()
            return f"{tag} ({commit_hash})"

        # Detached HEAD without tag
        return commit_hash

    except (subprocess.CalledProcessError, FileNotFoundError):
        # CalledProcessError → not a git repo
        # FileNotFoundError → git not installed
        return None


def _get_nested(d: dict, key: str) -> dict:
    """Get nested value from dict by dot-separated key path.

    Args:
        d: The dictionary to traverse
        key: Dot-separated path (e.g., "db.connection.host")

    Returns:
        The nested dict at the specified path

    Raises:
        KeyError: If any part of the path doesn't exist
    """
    result = d

    if not key:
        return d

    for part in key.split("."):
        if len(part) > 0:
            result = result.get(part, {})

    return result


def _read_toml(path: Path) -> dict:
    if not path.exists():
        return {}

    with open(path, "rb") as f:
        data = tomllib.load(f)

    return data.get("app", {})


def _convert_value(value: str) -> Any:
    """Convert string value by evaluating it safely."""
    try:
        return ast.literal_eval(value)
    except (ValueError, SyntaxError):
        return value  # Keep as string if not a literal


def _set_nested(d: dict, keys: list[str], value: Any) -> None:
    """Set nested value in dict by key path, creating dicts as needed."""
    for key in keys[:-1]:
        d = d.setdefault(key, {})
    d[keys[-1]] = value


def _merge_env_vars(config: dict, prefix: str = "APP__") -> dict:
    """Deep merge environment variables into config dict.

    Examples:
        APP__DEBUG=True              -> {"debug": True}
        APP__PORT=8080               -> {"port": 8080}
        APP__HOSTS=["a","b"]         -> {"hosts": ["a", "b"]}
        APP__DB__CONFIG={"x": 1}     -> {"db": {"config": {"x": 1}}}
    """
    result = dicts.deep_merge({}, config)

    for key, value in os.environ.items():
        if not key.startswith(prefix):
            continue

        key_path = key[len(prefix) :].lower().split("__")
        converted = _convert_value(value)
        _set_nested(result, key_path, converted)

    return result
