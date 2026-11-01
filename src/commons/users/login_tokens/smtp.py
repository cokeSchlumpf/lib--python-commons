"""
Sending login links and codes by email via SMTP.

``SMTPLoginTokenSender`` implements ``SendLoginTokenPort``: it connects to the
server of ``app.smtp`` (:class:`commons.settings.SMTPSettings`), always
encrypted, and sends one mail per login request.

The mail is built per message by a mail function (``ComposeLoginTokenMail``).
The default one fills ``string.Template`` templates with these placeholders:

- ``$name``: display name of the user, else the username
- ``$link``: the login link
- ``$code``: the login code
- ``$valid_minutes``: how long link and code are valid
- ``$expires_at``: when they expire, ``YYYY-MM-DD HH:MM UTC``

Write ``$$`` for a literal ``$``; braces (e.g. CSS) need no escaping. Subject
and text are built in for English (``"en"``) and German (``"de"``), chosen
with the ``language`` argument; there is no built-in HTML. An app overrides
them in ``app.login_tokens``::

    [app.login_tokens]
    mail_subject = "Your code for CaseSight: $code"
    mail_html = \"\"\"
    <p>Hello $name,</p>
    <p>your code is <strong>$code</strong>, or <a href="$link">sign in</a>.</p>
    \"\"\"

In the HTML, the values are HTML-escaped. For anything else (another language
per user, a template engine, a template file) pass your own mail function.

Wiring it into pyhx::

    sender = SMTPLoginTokenSender(language="de")  # reads app.smtp and app.login_tokens
    EmailTokenLogin(store=SQLLoginTokenStore(engine), sender=sender)
"""

import html
import smtplib
import ssl
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC
from email.message import EmailMessage
from email.utils import formatdate, make_msgid, parseaddr
from string import Template
from typing import Literal

from commons.settings import SMTPSettings
from commons.users.login_tokens.sender import LoginTokenMessage
from commons.users.login_tokens.service import LoginTokenSettings


@dataclass(frozen=True)
class LoginTokenMail:
    """
    The login mail to send.

    Attributes:
        subject: Subject line.
        text: Plain-text body.
        html: Optional HTML body; the mail then has both versions.
    """

    subject: str
    text: str
    html: str | None = None


ComposeLoginTokenMail = Callable[[LoginTokenMessage], LoginTokenMail]
"""Builds the login mail for a message, e.g. in the user's language."""

Language = Literal["en", "de"]

_BUILT_IN: dict[str, tuple[str, str]] = {
    "en": (
        "Your sign-in code: $code",
        "Hello $name,\n\n"
        "your sign-in code is $code.\n"
        "Or sign in with this link: $link\n\n"
        "The code and the link are valid for $valid_minutes minutes. "
        "If you didn't request them, ignore this email.\n",
    ),
    "de": (
        "Ihr Anmeldecode: $code",
        "Hallo $name,\n\n"
        "Ihr Anmeldecode lautet $code.\n"
        "Oder melden Sie sich mit diesem Link an: $link\n\n"
        "Code und Link sind $valid_minutes Minuten gültig. "
        "Wenn Sie sie nicht angefordert haben, ignorieren Sie diese E-Mail.\n",
    ),
}

_SAMPLE = {"name": "", "link": "", "code": "", "valid_minutes": "", "expires_at": ""}


def _template(setting: str, source: str) -> Template:
    template = Template(source)
    try:
        template.substitute(_SAMPLE)
    except KeyError as error:
        raise ValueError(f"Login mail `{setting}`: unknown placeholder ${error.args[0]}.") from None
    except ValueError as error:
        raise ValueError(f"Login mail `{setting}`: {error} (write $$ for a literal $).") from None
    return template


class _TemplateMail:
    """The default mail function: fills the templates of the settings or the built-in ones."""

    def __init__(self, settings: LoginTokenSettings, language: Language) -> None:
        subject, text = _BUILT_IN[language]
        self._subject = _template("mail_subject", settings.mail_subject or subject)
        self._text = _template("mail_text", settings.mail_text or text)
        self._html = _template("mail_html", settings.mail_html) if settings.mail_html else None
        self._valid_minutes = str(settings.token_ttl // 60)

    def __call__(self, message: LoginTokenMessage) -> LoginTokenMail:
        values = {
            "name": message.user.display_name or message.user.username,
            "link": message.link,
            "code": message.code,
            "valid_minutes": self._valid_minutes,
            "expires_at": message.expires_at.astimezone(UTC).strftime("%Y-%m-%d %H:%M UTC"),
        }
        return LoginTokenMail(
            subject=self._subject.substitute(values),
            text=self._text.substitute(values),
            html=self._html.substitute(_escaped(values)) if self._html else None,
        )


def _escaped(values: Mapping[str, str]) -> dict[str, str]:
    return {key: html.escape(value) for key, value in values.items()}


class SMTPLoginTokenSender:
    """
    Sends login links and codes by email via SMTP.

    Reads and checks its settings when it is created, so a misconfigured app
    fails at startup. Every delivery error is raised (connection, timeout,
    TLS, sign-in, refused sender or recipient); nothing is logged.

    Args:
        smtp: The SMTP connection; defaults to ``SMTPSettings.read()``.
        settings: The templates (``mail_subject``, ``mail_text``, ``mail_html``)
            and the validity; defaults to ``LoginTokenSettings.read()``. Not
            read if ``compose`` is given.
        compose: Builds the mail per message; defaults to the templates.
        language: Language of the built-in templates, ``"en"`` or ``"de"``.

    Raises:
        ValueError: If ``language`` is unknown or a template has an unknown
            placeholder or an invalid ``$``.
        pydantic.ValidationError: If ``app.smtp`` is missing or invalid.
    """

    def __init__(
        self,
        smtp: SMTPSettings | None = None,
        settings: LoginTokenSettings | None = None,
        compose: ComposeLoginTokenMail | None = None,
        language: Language = "en",
    ) -> None:
        if language not in _BUILT_IN:
            raise ValueError(f"Unknown language `{language}` of the login mail; use one of {sorted(_BUILT_IN)}.")
        self._smtp = smtp or SMTPSettings.read()
        self._compose = compose or _TemplateMail(settings or LoginTokenSettings.read(), language)

    def send_login_token(self, message: LoginTokenMessage) -> None:
        smtp = self._smtp
        mail = self._compose(message)

        email = EmailMessage()
        email["Subject"] = mail.subject
        email["From"] = smtp.from_address
        email["To"] = message.email
        email["Date"] = formatdate()
        email["Message-ID"] = make_msgid(domain=parseaddr(smtp.from_address)[1].rpartition("@")[2] or None)
        email.set_content(mail.text)
        if mail.html is not None:
            email.add_alternative(mail.html, subtype="html")

        context = ssl.create_default_context()
        connection: smtplib.SMTP
        if smtp.security == "ssl":
            connection = smtplib.SMTP_SSL(smtp.host, smtp.port or 465, timeout=smtp.timeout, context=context)
        else:
            connection = smtplib.SMTP(smtp.host, smtp.port or 587, timeout=smtp.timeout)

        with connection as server:
            if smtp.security == "starttls":
                server.starttls(context=context)  # raises SMTPNotSupportedError if not offered
            if smtp.username:
                server.login(smtp.username, smtp.password.get_secret_value())
            server.send_message(email)
