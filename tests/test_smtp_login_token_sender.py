import email
import smtplib
import socket
import ssl
from datetime import UTC, datetime
from email.message import EmailMessage
from typing import Any

import pytest
from pydantic import ValidationError

from commons.settings import SMTPSettings
from commons.users import RegisteredUser
from commons.users.login_tokens import (
    LoginTokenMail,
    LoginTokenMessage,
    LoginTokenSettings,
    SMTPLoginTokenSender,
)

LINK = "https://app.example.com/login/token?t=abc&x=1"
EXPIRES = datetime(2026, 11, 1, 9, 30, tzinfo=UTC)


class FakeServer:
    """Stand-in for ``smtplib.SMTP`` / ``SMTP_SSL``: records what the sender does."""

    instances: list["FakeServer"] = []
    starttls_offered = True
    fail: dict[str, Exception] = {}

    def __init__(self, host: str, port: int, *, timeout: float, context: ssl.SSLContext | None = None) -> None:
        if "connect" in self.fail:
            raise self.fail["connect"]
        self.host, self.port, self.timeout, self.context = host, port, timeout, context
        self.calls: list[str] = []
        self.tls_context: ssl.SSLContext | None = None
        self.login_args: tuple[str, str] | None = None
        self.sent: EmailMessage | None = None
        self.closed = False
        FakeServer.instances.append(self)

    def __enter__(self) -> "FakeServer":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.closed = True

    def starttls(self, *, context: ssl.SSLContext) -> None:
        self.calls.append("starttls")
        if not self.starttls_offered:
            raise smtplib.SMTPNotSupportedError("STARTTLS extension not supported by server.")
        if "starttls" in self.fail:
            raise self.fail["starttls"]
        self.tls_context = context

    def login(self, user: str, password: str) -> None:
        self.calls.append("login")
        if "login" in self.fail:
            raise self.fail["login"]
        self.login_args = (user, password)

    def send_message(self, message: EmailMessage) -> None:
        self.calls.append("send_message")
        if "send" in self.fail:
            raise self.fail["send"]
        self.sent = message


class FakeSSLServer(FakeServer):
    pass


@pytest.fixture(autouse=True)
def fake_smtplib(monkeypatch):
    FakeServer.instances = []
    FakeServer.starttls_offered = True
    FakeServer.fail = {}
    monkeypatch.setattr(smtplib, "SMTP", FakeServer)
    monkeypatch.setattr(smtplib, "SMTP_SSL", FakeSSLServer)


def smtp(**overrides: Any) -> SMTPSettings:
    values: dict[str, Any] = {
        "host": "smtp.example.com",
        "username": "login@example.com",
        "password": "s3cret",
        "from_address": "App <login@example.com>",
    }
    return SMTPSettings(**(values | overrides))


def message(display_name: str = "Jane Doe", locale: str | None = None) -> LoginTokenMessage:
    user = RegisteredUser.create("jane", None, display_name, email="jane@example.com")
    return LoginTokenMessage(
        user=user, email="jane@example.com", link=LINK, code="123456", expires_at=EXPIRES, locale=locale
    )


def send(sender: SMTPLoginTokenSender, msg: LoginTokenMessage | None = None) -> FakeServer:
    sender.send_login_token(msg or message())
    return FakeServer.instances[-1]


def parts(sent: EmailMessage | None) -> dict[str, str]:
    assert sent is not None
    parsed = email.message_from_bytes(bytes(sent), policy=email.policy.default)
    return {part.get_content_type(): part.get_content() for part in parsed.walk() if not part.is_multipart()}


class TestConnection:
    def test_starttls_connects_upgrades_signs_in_and_sends(self):
        server = send(SMTPLoginTokenSender(smtp(), LoginTokenSettings()))

        assert type(server) is FakeServer
        assert (server.host, server.port, server.timeout) == ("smtp.example.com", 587, 30)
        assert server.calls == ["starttls", "login", "send_message"]
        assert isinstance(server.tls_context, ssl.SSLContext)
        assert server.tls_context.verify_mode == ssl.CERT_REQUIRED
        assert server.tls_context.check_hostname
        assert server.login_args == ("login@example.com", "s3cret")
        assert server.closed

    def test_ssl_connects_with_tls_from_the_start(self):
        server = send(SMTPLoginTokenSender(smtp(security="ssl", timeout=5), LoginTokenSettings()))

        assert type(server) is FakeSSLServer
        assert (server.port, server.timeout) == (465, 5)
        assert server.context is not None and server.context.verify_mode == ssl.CERT_REQUIRED
        assert server.calls == ["login", "send_message"]

    def test_raises_if_starttls_is_not_offered(self):
        FakeServer.starttls_offered = False

        with pytest.raises(smtplib.SMTPNotSupportedError):
            send(SMTPLoginTokenSender(smtp(), LoginTokenSettings()))

        assert FakeServer.instances[-1].calls == ["starttls"]

    def test_without_username_it_does_not_sign_in(self):
        server = send(SMTPLoginTokenSender(smtp(username="", password=""), LoginTokenSettings()))

        assert server.calls == ["starttls", "send_message"]

    @pytest.mark.parametrize(
        ("step", "error"),
        [
            ("connect", ConnectionRefusedError("refused")),
            ("connect", socket.timeout("timed out")),
            ("starttls", ssl.SSLCertVerificationError("certificate verify failed")),
            ("login", smtplib.SMTPAuthenticationError(535, b"Authentication failed")),
            ("send", smtplib.SMTPSenderRefused(553, b"Sender not allowed", "login@example.com")),
            ("send", smtplib.SMTPRecipientsRefused({"jane@example.com": (550, b"No such user")})),
        ],
    )
    def test_every_failure_is_raised(self, step, error):
        FakeServer.fail = {step: error}

        with pytest.raises(type(error)):
            send(SMTPLoginTokenSender(smtp(), LoginTokenSettings()))

    def test_logs_neither_link_nor_code_nor_password(self, caplog):
        FakeServer.fail = {"login": smtplib.SMTPAuthenticationError(535, b"Authentication failed")}

        sender = SMTPLoginTokenSender(smtp(), LoginTokenSettings())

        with caplog.at_level("DEBUG"):
            with pytest.raises(smtplib.SMTPAuthenticationError) as error:
                send(sender)
            FakeServer.fail = {}
            send(sender)

        for secret in ("s3cret", "123456", LINK):
            assert secret not in caplog.text
            assert secret not in str(error.value)


class TestCreation:
    def test_reads_settings_when_created(self, clean_app_env, monkeypatch):
        monkeypatch.setenv("APP__SMTP__HOST", "smtp.strato.de")
        monkeypatch.setenv("APP__SMTP__FROM_ADDRESS", "login@example.com")
        monkeypatch.setenv("APP__LOGIN_TOKENS__MAIL_SUBJECT", "Code $code")

        server = send(SMTPLoginTokenSender())

        assert server.host == "smtp.strato.de"
        assert server.sent is not None and server.sent["Subject"] == "Code 123456"

    def test_fails_when_created_without_smtp_settings(self, clean_app_env, monkeypatch, tmp_path):
        monkeypatch.setattr("commons.path_operators.get_project_root_dir", lambda: tmp_path)
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path / "home")

        with pytest.raises(ValidationError, match="host"):
            SMTPLoginTokenSender()

    def test_rejects_an_unknown_language(self):
        with pytest.raises(ValueError, match="es"):
            SMTPLoginTokenSender(smtp(), LoginTokenSettings(), language="es")  # type: ignore[arg-type]

    @pytest.mark.parametrize(
        ("setting", "template", "match"),
        [
            ("mail_subject", "Code $kode", r"mail_subject.*\$kode"),
            ("mail_text", "Hello ${name", "mail_text"),
            ("mail_html", "<p>Costs 5 $</p>", "mail_html"),
        ],
    )
    def test_rejects_invalid_templates_when_created(self, setting, template, match):
        with pytest.raises(ValueError, match=match):
            SMTPLoginTokenSender(smtp(), LoginTokenSettings(**{setting: template}))


class TestMail:
    def test_default_mail_is_english_plain_text(self):
        server = send(SMTPLoginTokenSender(smtp(), LoginTokenSettings()))
        sent = server.sent
        assert sent is not None

        assert sent["Subject"] == "Your sign-in code: 123456"
        assert sent["From"] == "App <login@example.com>"
        assert sent["To"] == "jane@example.com"
        assert sent["Date"] and sent["Message-ID"].endswith("@example.com>")
        assert sent.get_content_type() == "text/plain"
        text = parts(sent)["text/plain"]
        assert text.startswith("Hello Jane Doe,")
        assert "123456" in text and LINK in text and "valid for 15 minutes" in text

    def test_default_mail_in_german(self):
        server = send(SMTPLoginTokenSender(smtp(), LoginTokenSettings(token_ttl=600), language="de"))
        sent = server.sent
        assert sent is not None

        assert sent["Subject"] == "Ihr Anmeldecode: 123456"
        text = parts(sent)["text/plain"]
        assert text.startswith("Hallo Jane Doe,")
        assert "10 Minuten gültig" in text

    @pytest.mark.parametrize(
        ("language", "subject", "greeting"),
        [
            ("en", "Your sign-in code: 123456", "Hello Jane Doe,"),
            ("de", "Ihr Anmeldecode: 123456", "Hallo Jane Doe,"),
            ("it", "Il tuo codice di accesso: 123456", "Ciao Jane Doe,"),
            ("fr", "Votre code de connexion : 123456", "Bonjour Jane Doe,"),
        ],
    )
    def test_built_in_mail_per_language(self, language, subject, greeting):
        server = send(SMTPLoginTokenSender(smtp(), LoginTokenSettings(), language=language))

        assert server.sent is not None and server.sent["Subject"] == subject
        text = parts(server.sent)["text/plain"]
        assert text.startswith(greeting) and "123456" in text and LINK in text and "15" in text

    @pytest.mark.parametrize(
        ("locale", "subject"),
        [
            ("it", "Il tuo codice di accesso: 123456"),
            ("de-CH", "Ihr Anmeldecode: 123456"),
            ("fr_FR", "Votre code de connexion : 123456"),
            ("es", "Your sign-in code: 123456"),
            (None, "Your sign-in code: 123456"),
        ],
    )
    def test_mail_in_the_language_of_the_message_else_of_the_sender(self, locale, subject):
        server = send(SMTPLoginTokenSender(smtp(), LoginTokenSettings()), message(locale=locale))

        assert server.sent is not None and server.sent["Subject"] == subject

    def test_templates_from_settings_apply_to_every_language(self):
        sender = SMTPLoginTokenSender(smtp(), LoginTokenSettings(mail_subject="Code $code"))

        for locale in ("en", "de", "it", "fr"):
            server = send(sender, message(locale=locale))
            assert server.sent is not None and server.sent["Subject"] == "Code 123456"

    def test_name_falls_back_to_the_username(self):
        server = send(SMTPLoginTokenSender(smtp(), LoginTokenSettings()), message(display_name=""))

        assert parts(server.sent)["text/plain"].startswith("Hello jane,")

    def test_templates_from_settings_win_over_the_language(self):
        settings = LoginTokenSettings(
            mail_subject="Code für $name",
            mail_text="$code bis $expires_at, $$5",
            mail_html='<style>a { color: red }</style><a href="$link">$name</a> $code',
        )

        server = send(SMTPLoginTokenSender(smtp(), settings, language="de"), message(display_name="<Jane & Co>"))
        sent = server.sent
        assert sent is not None

        assert sent["Subject"] == "Code für <Jane & Co>"
        assert sent.get_content_type() == "multipart/alternative"
        body = parts(sent)
        assert body["text/plain"].strip() == "123456 bis 2026-11-01 09:30 UTC, $5"
        assert body["text/html"].strip() == (
            '<style>a { color: red }</style>'
            '<a href="https://app.example.com/login/token?t=abc&amp;x=1">&lt;Jane &amp; Co&gt;</a> 123456'
        )

    def test_custom_mail_function(self):
        def compose(msg: LoginTokenMessage) -> LoginTokenMail:
            return LoginTokenMail(subject=f"Hi {msg.user.username}", text=msg.code, html=f"<b>{msg.code}</b>")

        server = send(SMTPLoginTokenSender(smtp(), compose=compose))
        sent = server.sent
        assert sent is not None

        assert sent["Subject"] == "Hi jane"
        assert parts(sent) == {"text/plain": "123456\n", "text/html": "<b>123456</b>\n"}
