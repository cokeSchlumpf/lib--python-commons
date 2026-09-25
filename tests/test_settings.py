from pathlib import Path
from unittest.mock import patch

import pytest

from commons.settings import (
    read_settings,
    read_settings_object,
    _convert_value,
    _get_nested,
    _set_nested,
    _merge_env_vars,
)


class TestConvertValue:
    def test_converts_int(self):
        assert _convert_value("42") == 42

    def test_converts_float(self):
        assert _convert_value("3.14") == 3.14

    def test_converts_bool_true(self):
        assert _convert_value("True") is True

    def test_converts_bool_false(self):
        assert _convert_value("False") is False

    def test_converts_list(self):
        assert _convert_value('["a", "b"]') == ["a", "b"]

    def test_converts_dict(self):
        assert _convert_value('{"x": 1}') == {"x": 1}

    def test_keeps_string_when_not_literal(self):
        assert _convert_value("hello world") == "hello world"

    def test_keeps_string_for_invalid_syntax(self):
        assert _convert_value("[invalid") == "[invalid"


class TestSetNested:
    def test_single_key(self):
        d = {}
        _set_nested(d, ["foo"], "bar")
        assert d == {"foo": "bar"}

    def test_nested_keys(self):
        d = {}
        _set_nested(d, ["a", "b", "c"], "value")
        assert d == {"a": {"b": {"c": "value"}}}

    def test_creates_intermediate_dicts(self):
        d = {"existing": 1}
        _set_nested(d, ["new", "nested"], "value")
        assert d == {"existing": 1, "new": {"nested": "value"}}

    def test_overwrites_existing_value(self):
        d = {"a": {"b": "old"}}
        _set_nested(d, ["a", "b"], "new")
        assert d == {"a": {"b": "new"}}


class TestMergeEnvVars:
    def test_simple_env_var(self, clean_app_env, monkeypatch):
        monkeypatch.setenv("APP__DEBUG", "True")
        result = _merge_env_vars({})
        assert result["debug"] is True

    def test_nested_env_var(self, clean_app_env, monkeypatch):
        monkeypatch.setenv("APP__DB__HOST", "localhost")
        result = _merge_env_vars({})
        assert result == {"db": {"host": "localhost"}}

    def test_overrides_existing_config(self, clean_app_env, monkeypatch):
        monkeypatch.setenv("APP__PORT", "9000")
        config = {"port": 8080}
        result = _merge_env_vars(config)
        assert result["port"] == 9000

    def test_ignores_non_prefixed_vars(self, clean_app_env, monkeypatch):
        monkeypatch.setenv("OTHER_VAR", "value")
        result = _merge_env_vars({})
        assert "other_var" not in result

    def test_does_not_mutate_input(self, clean_app_env, monkeypatch):
        monkeypatch.setenv("APP__NEW", "value")
        config = {"existing": 1}
        _merge_env_vars(config)
        assert config == {"existing": 1}


class TestReadSettings:
    def test_loads_from_pyproject_toml(self, tmp_path, clean_app_env):
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text('[app]\nfoo = "bar"\n')

        with patch("commons.path_operators.get_project_root_dir", return_value=tmp_path):
            with patch.object(Path, "home", return_value=tmp_path / "nonexistent_home"):
                result = read_settings()

        assert result.get("foo") == "bar"

    def test_loads_from_settings_toml(self, tmp_path, clean_app_env):
        settings = tmp_path / "settings.toml"
        settings.write_text('[app]\nkey = "value"\n')

        with patch("commons.path_operators.get_project_root_dir", return_value=tmp_path):
            with patch.object(Path, "home", return_value=tmp_path / "nonexistent_home"):
                result = read_settings()

        assert result.get("key") == "value"

    def test_environment_specific_file(self, tmp_path, clean_app_env, monkeypatch):
        monkeypatch.setenv("APP__ENVIRONMENT", "production")

        settings_prod = tmp_path / "settings.production.toml"
        settings_prod.write_text('[app]\nenv = "prod"\n')

        with patch("commons.path_operators.get_project_root_dir", return_value=tmp_path):
            with patch.object(Path, "home", return_value=tmp_path / "nonexistent_home"):
                result = read_settings()

        assert result.get("env") == "prod"

    def test_later_files_override_earlier(self, tmp_path, clean_app_env):
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text('[app]\nkey = "from_pyproject"\n')

        settings = tmp_path / "settings.toml"
        settings.write_text('[app]\nkey = "from_settings"\n')

        with patch("commons.path_operators.get_project_root_dir", return_value=tmp_path):
            with patch.object(Path, "home", return_value=tmp_path / "nonexistent_home"):
                result = read_settings()

        assert result.get("key") == "from_settings"

    def test_secrets_file_loaded(self, tmp_path, clean_app_env):
        secrets = tmp_path / ".secrets.toml"
        secrets.write_text('[app]\nsecret = "hidden"\n')

        with patch("commons.path_operators.get_project_root_dir", return_value=tmp_path):
            with patch.object(Path, "home", return_value=tmp_path / "nonexistent_home"):
                result = read_settings()

        assert result.get("secret") == "hidden"

    def test_missing_files_handled_gracefully(self, tmp_path, clean_app_env):
        with patch("commons.path_operators.get_project_root_dir", return_value=tmp_path):
            with patch.object(Path, "home", return_value=tmp_path / "nonexistent_home"):
                result = read_settings()

        assert result == {}

    def test_env_vars_override_file_config(self, tmp_path, clean_app_env, monkeypatch):
        monkeypatch.setenv("APP__KEY", "from_env")

        settings = tmp_path / "settings.toml"
        settings.write_text('[app]\nkey = "from_file"\n')

        with patch("commons.path_operators.get_project_root_dir", return_value=tmp_path):
            with patch.object(Path, "home", return_value=tmp_path / "nonexistent_home"):
                result = read_settings()

        assert result.get("key") == "from_env"

    def test_nested_config_merging(self, tmp_path, clean_app_env):
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text('[app.db]\nhost = "localhost"\nport = 5432\n')

        settings = tmp_path / "settings.toml"
        settings.write_text('[app.db]\nhost = "production"\n')

        with patch("commons.path_operators.get_project_root_dir", return_value=tmp_path):
            with patch.object(Path, "home", return_value=tmp_path / "nonexistent_home"):
                result = read_settings()

        assert result["db"]["host"] == "production"
        assert result["db"]["port"] == 5432

    def test_user_home_settings(self, tmp_path, clean_app_env):
        home_dir = tmp_path / "home"
        wellner_dir = home_dir / ".wellner"
        wellner_dir.mkdir(parents=True)
        user_settings = wellner_dir / "settings.toml"
        user_settings.write_text('[app]\nuser_key = "user_value"\n')

        with patch("commons.path_operators.get_project_root_dir", return_value=tmp_path):
            with patch.object(Path, "home", return_value=home_dir):
                result = read_settings()

        assert result.get("user_key") == "user_value"

    def test_caching_returns_same_result(self, tmp_path, clean_app_env):
        settings = tmp_path / "settings.toml"
        settings.write_text('[app]\nkey = "value"\n')

        with patch("commons.path_operators.get_project_root_dir", return_value=tmp_path):
            with patch.object(Path, "home", return_value=tmp_path / "nonexistent_home"):
                result1 = read_settings()
                result2 = read_settings()

        assert result1 is result2


class TestGetNested:
    def test_single_level(self):
        d = {"foo": "bar"}
        assert _get_nested(d, "foo") == "bar"

    def test_multiple_levels(self):
        d = {"a": {"b": {"c": "value"}}}
        assert _get_nested(d, "a.b.c") == "value"

    def test_returns_nested_dict(self):
        d = {"db": {"host": "localhost", "port": 5432}}
        assert _get_nested(d, "db") == {"host": "localhost", "port": 5432}


class TestReadSettingsObject:
    def test_with_dataclass(self, tmp_path, clean_app_env):
        from dataclasses import dataclass

        @dataclass
        class DbConfig:
            host: str
            port: int

        settings = tmp_path / "settings.toml"
        settings.write_text('[app.db]\nhost = "localhost"\nport = 5432\n')

        with patch("commons.path_operators.get_project_root_dir", return_value=tmp_path):
            with patch.object(Path, "home", return_value=tmp_path / "nonexistent_home"):
                result = read_settings_object("db", DbConfig)

        assert isinstance(result, DbConfig)
        assert result.host == "localhost"
        assert result.port == 5432

    def test_with_nested_key(self, tmp_path, clean_app_env):
        from dataclasses import dataclass

        @dataclass
        class ChromaConfig:
            directory: str

        settings = tmp_path / "settings.toml"
        settings.write_text('[app.vectorstore.chroma]\ndirectory = "/data/chroma"\n')

        with patch("commons.path_operators.get_project_root_dir", return_value=tmp_path):
            with patch.object(Path, "home", return_value=tmp_path / "nonexistent_home"):
                result = read_settings_object("vectorstore.chroma", ChromaConfig)

        assert result.directory == "/data/chroma"

    def test_with_pydantic_like_model_validate(self, tmp_path, clean_app_env):
        class PydanticLikeModel:
            def __init__(self, host: str, port: int):
                self.host = host
                self.port = port

            @classmethod
            def model_validate(cls, data: dict):
                return cls(host=data["host"].upper(), port=data["port"])

        settings = tmp_path / "settings.toml"
        settings.write_text('[app.db]\nhost = "localhost"\nport = 5432\n')

        with patch("commons.path_operators.get_project_root_dir", return_value=tmp_path):
            with patch.object(Path, "home", return_value=tmp_path / "nonexistent_home"):
                result = read_settings_object("db", PydanticLikeModel)

        assert isinstance(result, PydanticLikeModel)
        assert result.host == "LOCALHOST"
        assert result.port == 5432
