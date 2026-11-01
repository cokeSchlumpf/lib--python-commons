# T-005 SMTP sender for login tokens

## Problem

`commons.users.login_tokens` defines the port `SendLoginTokenPort`, but its only implementation is `LoggingLoginTokenSender`, which writes link and code to the log. An app that is deployed can therefore not send its users the login mail: `app--casesight` runs on UAT, but nobody can sign in, because users sign in by email only. Every app with email login (pyhx `EmailTokenLogin`) would have to write its own mail sender, and the pyhx guide only says "Implement `SendLoginTokenPort` to send real emails".

## Proposed outcome

- `commons` offers an `SMTPLoginTokenSender` that implements `SendLoginTokenPort` and delivers link and code as an email via SMTP, so every app can reuse it instead of writing its own.
- The SMTP connection (host, port, TLS mode, user, password, sender address) is configured through `commons.settings` under `app.smtp.*` (`APP__SMTP__HOST`, `APP__SMTP__PASSWORD`, …), so an app sets it in its settings files locally and through `APP__*` variables (password from the Key Vault) when deployed. A generic SMTP settings class reads them; it isn't specific to login, so other mail senders can reuse it later.
- It works with a Strato mailbox (`smtp.strato.de`, SSL on 465 or STARTTLS on 587, user and password), the first one in use, and with other SMTP servers that use the same mechanisms.
- The mail is plain text by default, with link, code and expiry; an app can override subject and body under `app.login_tokens.*` and can add an HTML version.
- The mail is built per message by a replaceable function that gets the `LoginTokenMessage` (with the user) and returns subject, text and optional HTML, so an app can choose the wording, e.g. by the language in the user record. Passing request context (such as the browser's language) from pyhx into the login request is out of scope (backlog T-006).
- Delivery errors are raised, as the port requires, so the caller can tell the user to try again.
- It deliberately doesn't wire the sender into `app--casesight` (its own change there), doesn't set up the deployment settings (Terraform / Key Vault, a later change), and isn't a general mailing API.

## Affected users and systems

- **Apps with email login (first `app--casesight`):** can replace `LoggingLoginTokenSender` with the SMTP sender and a few settings.
- **Users of these apps:** receive the login link and code by email and can sign in on deployed instances.
- **`commons`:** a new sender in `commons.users.login_tokens`, new settings, a minor release on `versions/1`.
- **pyhx:** its user-authentication guide can point to the new sender instead of "implement it yourself".

## Constraints

- Backward compatible within major version 1: `LoggingLoginTokenSender` stays the default; nothing changes for apps that don't configure SMTP.
- No new dependency: the standard library (`smtplib`, `email`) is enough; synchronous like the rest of `commons.users`.
- Secrets (the SMTP password) are never committed or logged; locally in `settings.secrets.toml`, in Azure as `APP__*` app settings from the Key Vault. Link and code are not written to the log either.
- Connections are encrypted (SSL or STARTTLS); no plain-text fallback.
- Settings follow the existing conventions of `commons.settings` (`app.*`, env var overrides) and are documented.
- Strato only accepts mails whose sender address belongs to the mailbox; the sender address is a setting.

## Open questions

None.
