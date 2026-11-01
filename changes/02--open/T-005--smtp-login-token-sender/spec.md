# T-005 SMTP sender for login tokens: spec

## Requirements

### SMTP settings

- **R1** `SMTPSettings` in `commons.settings` holds the SMTP connection: `host`, `port`, `security` (`ssl` or `starttls`), `username`, `password`, `from_address` (e.g. `CaseSight <login@example.com>`) and `timeout` (seconds). `SMTPSettings.read()` reads them from `app.smtp.*`; every key can be set with an env var (`APP__SMTP__PASSWORD`, …).
- **R2** `port` defaults to 465 for `ssl` and 587 for `starttls`; `timeout` defaults to 30 seconds; `username` and `password` are optional (no login without a username).
- **R3** `SMTPSettings.read()` raises an error naming the missing keys if `app.smtp` is missing or `host` or `from_address` is empty; an unknown `security` value is rejected with a validation error.
- **R4** The password never appears in `repr()` or `str()` of the settings, nor in a log line or error message written by `commons`.

### Sender

- **R5** `SMTPLoginTokenSender` in `commons.users.login_tokens` implements `SendLoginTokenPort`. It takes the SMTP settings (default `SMTPSettings.read()`), the login-token settings (default `LoginTokenSettings.read()`) and optionally a function that builds the mail; it reads and checks all of them when it is created, so a misconfigured app fails at startup, not at the first login.
- **R6** `send_login_token(message)` sends one mail to `message.email` with `from_address` as sender and subject, text and optional HTML from the mail function.
- **R7** With `ssl` it connects with TLS from the start; with `starttls` it connects and upgrades with STARTTLS, and raises if the server doesn't offer STARTTLS. Server certificates are verified (the default SSL context). It never sends without TLS.
- **R8** If a username is set, it signs in with username and password before sending.
- **R9** Every failure (connection, timeout, TLS, sign-in, rejected sender or recipient) raises from `send_login_token`; nothing is swallowed. A connection or server that doesn't answer fails after `timeout`.
- **R10** The sender logs neither link nor code nor password.

### Mail content

- **R11** The mail function gets the `LoginTokenMessage` and returns a `LoginTokenMail` (`subject`, `text`, `html: str | None`); an app can pass its own, e.g. to choose the language from the user record.
- **R12** The default mail function builds the mail from `string.Template` templates (`$code` or `${code}`, `$$` for a literal `$`) with the placeholders `$name` (display name, else username), `$link`, `$code`, `$valid_minutes` and `$expires_at` (UTC, `YYYY-MM-DD HH:MM UTC`). Subject and text are built in for English and German, chosen by the app in code with the constructor argument `language` of the sender (`"en"` or `"de"`, default `"en"`; another value raises when the sender is created); there is no built-in HTML.
- **R13** An app overrides subject, text and HTML with `app.login_tokens.mail_subject`, `mail_text` and `mail_html`; a template that is set wins over the built-in one of the language. A template with an unknown placeholder or an invalid `$` raises when the sender is created (R5).
- **R14** In the HTML version, the inserted values are HTML-escaped; braces (e.g. CSS) need no escaping.
- **R15** Without HTML the mail is `text/plain` (UTF-8); with HTML it is `multipart/alternative` with the text and the HTML part.

### Compatibility, tests and documentation

- **R16** Existing behaviour doesn't change: `LoggingLoginTokenSender` stays the default of `LoginTokenService`, existing settings keep their meaning, and nothing is required of apps that don't use the new sender. No new dependency.
- **R17** Tests cover R1–R15 against a stand-in for `smtplib` that records connection, TLS, sign-in and the sent message: both security modes, STARTTLS not offered, sign-in with and without username, every failure kind of R9 raised, missing and invalid settings, env var override of the password, default mail in English and German, other `language` values rejected, overridden templates, custom mail function, unknown placeholder and invalid `$`, HTML escaping, CSS braces in HTML, and no secret in the log or `repr()`.
- **R18** The docstrings of `commons.users.login_tokens` (module, `SMTPLoginTokenSender`, `LoginTokenMail`, `LoginTokenSettings`) and of `SMTPSettings` describe the settings with a TOML example (Strato included) and how to wire the sender into `LoginTokenService` / pyhx `EmailTokenLogin`. `poe check` and `poe docs-build` pass.

## Design

No new dependency: `smtplib`, `ssl`, `email.message.EmailMessage`, `html` and `string.Template` of the standard library; synchronous like `commons.users` (pyhx already calls `request_login` via `asyncio.to_thread`).

### `SMTPSettings` (`commons/settings.py`)

A Pydantic model like `StandardUserSettings` (validation of `security`, `SecretStr` for the password, which masks it in `repr()`):

```python
class SMTPSettings(BaseModel):
    host: str
    port: int | None = None            # None → 465 (ssl) / 587 (starttls)
    security: Literal["ssl", "starttls"] = "starttls"
    username: str = ""
    password: SecretStr = SecretStr("")
    from_address: str
    timeout: float = 30

    @staticmethod
    def read() -> "SMTPSettings":      # read_settings_object("smtp", SMTPSettings); KeyError → clear error
```

```toml
[app.smtp]                              # settings.toml
host = "smtp.strato.de"
security = "ssl"                        # port 465
username = "login@example.com"
from_address = "CaseSight <login@example.com>"

# settings.secrets.toml / APP__SMTP__PASSWORD
[app.smtp]
password = "…"
```

### Sender and mail (`commons/users/login_tokens/smtp.py`)

```python
@dataclass(frozen=True)
class LoginTokenMail:
    subject: str
    text: str
    html: str | None = None

ComposeLoginTokenMail = Callable[[LoginTokenMessage], LoginTokenMail]

class SMTPLoginTokenSender:
    def __init__(self, smtp: SMTPSettings | None = None,
                 settings: LoginTokenSettings | None = None,
                 compose: ComposeLoginTokenMail | None = None,
                 language: Literal["en", "de"] = "en") -> None: ...
    def send_login_token(self, message: LoginTokenMessage) -> None: ...
```

- `__init__` reads the settings if not given, and with no `compose` builds the default one from the templates of `LoginTokenSettings`; it substitutes the templates once with sample values (`Template.substitute`) to fail on unknown placeholders and invalid `$` (R13); in HTML the values are passed through `html.escape` (R14).
- `send_login_token` composes the `EmailMessage` (`set_content(text)`, `add_alternative(html, subtype="html")` if HTML), opens `smtplib.SMTP_SSL(host, port, timeout, context=ssl.create_default_context())` or `smtplib.SMTP(...)` + `starttls(context=…)` (smtplib raises `SMTPNotSupportedError` if the server doesn't offer it), `login()` if a username is set, `send_message()`, all in a `with` block. Errors propagate.
- `LoginTokenSettings` gets three new optional keyword arguments: `mail_subject`, `mail_text` and `mail_html` (`None`: the built-in template of the sender's `language`, no HTML); `valid_minutes` is `token_ttl // 60`. The built-in templates are constants in `smtp.py`, one subject and text per language.

Built-in templates:

```
Subject: Your sign-in code: $code

Hello $name,

your sign-in code is $code.
Or sign in with this link: $link

The code and the link are valid for $valid_minutes minutes. If you didn't request them, ignore this email.
```

```
Subject: Ihr Anmeldecode: $code

Hallo $name,

Ihr Anmeldecode lautet $code.
Oder melden Sie sich mit diesem Link an: $link

Code und Link sind $valid_minutes Minuten gültig. Wenn Sie sie nicht angefordert haben, ignorieren Sie diese E-Mail.
```

An HTML template in an app's settings:

```toml
[app.login_tokens]
mail_html = """
<p>Hallo $name,</p>
<p>Ihr Anmeldecode lautet <strong>$code</strong>.</p>
<p><a href="$link">Jetzt anmelden</a></p>
"""
```

An app that keeps its template in a file reads it itself and passes `LoginTokenSettings(mail_html=…)`, or renders the mail in its own mail function (R11), with any template engine it likes.

`SMTPLoginTokenSender`, `LoginTokenMail` and `ComposeLoginTokenMail` are exported from `commons.users.login_tokens`; `SMTPSettings` from `commons.settings`.

### Wiring in an app (documented, not part of this change)

```python
sender = SMTPLoginTokenSender(language="de")   # reads app.smtp and app.login_tokens
EmailTokenLogin(store=SQLLoginTokenStore(engine), sender=sender)
```

## Alternatives considered

- **`aiosmtplib` / an async sender:** a new dependency, and the port and `LoginTokenService` are synchronous; pyhx already runs them in a thread.
- **A provider API (Azure Communication Services, Microsoft Graph, SendGrid):** provider-specific with its own SDK; the mailbox in use is Strato, which speaks SMTP.
- **`str.format` placeholders (`{code}`):** every `{` in the HTML, e.g. in CSS, would have to be doubled, which is easy to get wrong; `string.Template` doesn't clash with braces.
- **A template engine (Jinja2, Mustache via `chevron` or `pystache`):** a new runtime dependency (Jinja2 is only in the `docs` group; the Mustache libraries are barely maintained) for a mail without logic; an app that wants one uses it in its own mail function (R11). An optional extra `commons[mail]` with Jinja2 was considered and not chosen.
- **The language as a setting (`app.login_tokens.mail_language`):** the developer wants the language chosen in code, where the sender is created; a separate factory method per language (`SMTPLoginTokenSender.german()`) would add one method per language for what one argument does.
- **A setting with a template file path:** an app can read the file itself; nobody needs to switch templates without a code change.
- **Templates only in settings, no mail function:** can't choose the language per user (intent Q2).
- **Subclassing the sender to change the mail:** a function is the smaller interface and is enough.
- **SMTP settings under `app.login_tokens`:** rejected in the intent (Q1); the connection isn't specific to login.

## Constraint mapping

| Constraint (intent) | Met by |
| --- | --- |
| Backward compatible within major version 1 | R16; only additions to `commons.settings`, `LoginTokenSettings` and `commons.users.login_tokens` |
| No new dependency, standard library, synchronous | R16, design |
| Secrets never committed or logged; link and code not logged | R4, R10; password from `settings.secrets.toml` or `APP__SMTP__PASSWORD` (R1) |
| Encrypted connections, no plain-text fallback | R7 |
| Settings follow the conventions of `commons.settings` and are documented | R1, R3, R18 |
| Strato: sender address belongs to the mailbox | `from_address` (R1), documented with a Strato example (R18) |
| Delivery errors are raised | R9 |

## Open questions

None.

## Areas of concern

1. **Real delivery through Strato** (R6–R8): the tests use a stand-in for `smtplib` and can't show that Strato accepts the connection, the sign-in and the sender address, or that the mail doesn't land in spam. Handled by a manual test with a real Strato mailbox before the release (a short script with credentials from `settings.secrets.toml`, not committed). Owner: Michael Wellner.
2. **Outbound SMTP from Azure App Service** (R7): Azure blocks port 25, but not 465 or 587; to be confirmed when casesight is deployed with the sender. Owner: Michael Wellner (casesight change).
3. **Error details in logs** (R4, R9, R10): pyhx logs the sender's exception with its traceback; `smtplib` errors carry the server's reply, not the password, and the message isn't part of them. Tested by R17 (no secret in the log). Owner: Michael Wellner.
4. **Slow mail server blocks the login request** (R9): the user waits until the mail is sent; bounded by `timeout` (30 seconds). Owner: Michael Wellner.

## Out of scope

- Wiring the sender into `app--casesight` (its own change there) and setting up the deployment settings (Terraform / Key Vault, a later change).
- A general mailing API or other mails than the login mail; `SMTPSettings` can be reused for them later.
- Request context such as the browser's language in the login mail (backlog T-006).
- Retries, queues or sending in the background.
- The pyhx guide (`docs/guides/user-authentication.md`); the developer updates it later.
