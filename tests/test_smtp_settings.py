from pathlib import Path
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from commons.settings import SMTPSettings


@pytest.fixture(autouse=True)
def isolated_settings(clean_app_env, tmp_path, monkeypatch):
    """Read settings only from env vars: no project files, no ~/.wellner."""
    monkeypatch.setattr("commons.path_operators.get_project_root_dir", lambda: tmp_path)
    with patch.object(Path, "home", return_value=tmp_path / "home"):
        yield


def configure(monkeypatch, **values: str) -> None:
    for key, value in values.items():
        monkeypatch.setenv(f"APP__SMTP__{key.upper()}", value)


def test_reads_settings_from_toml(tmp_path):
    (tmp_path / "settings.toml").write_text(
        '[app.smtp]\nhost = "smtp.strato.de"\nsecurity = "ssl"\nusername = "login@example.com"\n'
        'from_address = "App <login@example.com>"\n'
    )
    (tmp_path / "settings.secrets.toml").write_text('[app.smtp]\npassword = "s3cret"\n')

    smtp = SMTPSettings.read()

    assert (smtp.host, smtp.port, smtp.security, smtp.username) == ("smtp.strato.de", 465, "ssl", "login@example.com")
    assert smtp.from_address == "App <login@example.com>"
    assert smtp.password.get_secret_value() == "s3cret"
    assert smtp.timeout == 30


def test_reads_settings_from_env_vars(monkeypatch):
    configure(monkeypatch, host="mail.example.com", from_address="a@example.com", password="s3cret", port="2525")

    smtp = SMTPSettings.read()

    assert (smtp.host, smtp.port, smtp.security) == ("mail.example.com", 2525, "starttls")
    assert smtp.password.get_secret_value() == "s3cret"
    assert smtp.username == ""


@pytest.mark.parametrize(("security", "port"), [("ssl", 465), ("starttls", 587)])
def test_port_defaults_to_the_security_mode(monkeypatch, security, port):
    configure(monkeypatch, host="h", from_address="a@example.com", security=security)

    assert SMTPSettings.read().port == port


def test_missing_section_names_the_required_keys():
    with pytest.raises(ValidationError) as error:
        SMTPSettings.read()

    assert {e["loc"][0] for e in error.value.errors()} == {"host", "from_address"}


def test_missing_keys_are_named(monkeypatch):
    configure(monkeypatch, username="u")

    with pytest.raises(ValidationError) as error:
        SMTPSettings.read()

    assert {e["loc"][0] for e in error.value.errors()} == {"host", "from_address"}


def test_empty_host_is_rejected(monkeypatch):
    configure(monkeypatch, host="''", from_address="a@example.com")

    with pytest.raises(ValidationError, match="host"):
        SMTPSettings.read()


def test_unknown_security_is_rejected(monkeypatch):
    configure(monkeypatch, host="h", from_address="a@example.com", security="none")

    with pytest.raises(ValidationError, match="security"):
        SMTPSettings.read()


def test_numeric_env_password_is_rejected_not_converted(monkeypatch):
    configure(monkeypatch, host="h", from_address="a@example.com", password="123456")

    with pytest.raises(ValidationError, match="APP__SMTP__PASSWORD"):
        SMTPSettings.read()


def test_quoted_numeric_env_password_is_accepted(monkeypatch):
    configure(monkeypatch, host="h", from_address="a@example.com", password='"123456"')

    assert SMTPSettings.read().password.get_secret_value() == "123456"


def test_password_is_not_shown():
    smtp = SMTPSettings(host="h", from_address="a@example.com", password="s3cret")

    assert "s3cret" not in repr(smtp)
    assert "s3cret" not in str(smtp)
