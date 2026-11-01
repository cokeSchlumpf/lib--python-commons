# T-005 SMTP sender for login tokens: plan

## Findings while planning

- **F1** `commons.settings` converts every `APP__*` value with `ast.literal_eval`: `APP__SMTP__PASSWORD=123456` becomes the int `123456`, `1_000` becomes `1000`, `"abc"` loses its quotes. Converting such a value back to `str` can silently change a password. `SMTPSettings` therefore rejects non-string values for `password`, `username` and `from_address` with an error that says to quote the value (`APP__SMTP__PASSWORD='"123456"'`), instead of guessing.
- **F2** pyhx calls `LoginTokenService.request_login` via `asyncio.to_thread` and catches the sender's exception with `LOG.exception(...)`, so a synchronous sender that raises fits the existing flow (R9).
- **F3** The tests clear the settings cache per test (`tests/conftest.py`), set settings through `monkeypatch.setenv("APP__…")` and patch `Path.home` to keep `~/.wellner/settings.toml` out; the new tests do the same.
- **F4** A release moves `versions/1` to the new release (reusable workflow `python-release.yml` of `core--devops-workflows`); the Release PR is opened by release-please after the merge to `main`.
- **F5** No Strato credentials are available to the agent; the manual delivery test of concern 1 can't be run here.
- **F6** `read_settings_object` doesn't raise `KeyError` for a missing section, although `_get_nested` documents it: it returns `{}`. `SMTPSettings.read()` therefore relies on Pydantic, whose error names the missing `host` and `from_address` (R3). `_get_nested` is left as it is, as other settings rely on getting `{}`.

Deviations from the spec:

- **D1** R1/R3: non-string `password`, `username` or `from_address` (F1) is rejected with a validation error instead of being converted.

## Branching

Branch `feature/smtp-login-token-sender`, draft PR #32. The developer accepted the plan in advance and waived the review after each step for this change: the steps are implemented and committed one after the other, the PR is closed out with `close-change`, squash-merged, and the Release PR is merged afterwards.

## Steps

### 1. SMTP settings

- `SMTPSettings` (Pydantic, `SecretStr` password, `security` literal, port defaults, string check of F1) and `SMTPSettings.read()`, whose validation error names missing `host` or `from_address` (also when `app.smtp` is missing, F6), in `commons/settings.py`; exported there. **R1, R2, R3, R4, D1**
- Proof: `tests/test_smtp_settings.py`: read from TOML and from `APP__SMTP__*`, port defaults per mode, missing section and missing keys named in the error, unknown `security` rejected, numeric env password rejected and quoted one accepted, password not in `repr()`/`str()`.

### 2. Sender and mail

- `commons/users/login_tokens/smtp.py`: `LoginTokenMail`, `ComposeLoginTokenMail`, built-in English and German templates (`string.Template`), the default mail function, and `SMTPLoginTokenSender(smtp, settings, compose, language)` with checks at creation and sending via `smtplib` (`SMTP_SSL` or `SMTP` + `starttls`, default SSL context, `login` if a username is set, `send_message`, timeout). `LoginTokenSettings` gets `mail_subject`, `mail_text`, `mail_html`. Exports in `commons.users.login_tokens`. **R5–R16**
- Proof: `tests/test_smtp_login_token_sender.py` against a stand-in for `smtplib.SMTP` / `SMTP_SSL` (monkeypatched): both modes with host, port, timeout and SSL context; STARTTLS not offered raises; login with and without username; each failure kind raised (connect, timeout, TLS, auth, recipient refused); text-only and multipart mail with subject, from, to; English and German default; other language rejected; template overrides from settings; custom mail function; unknown placeholder and invalid `$` rejected at creation; HTML escaping and CSS braces; no code, link or password in the log (`caplog`). Existing login-token tests unchanged and green (R16).

### 3. Documentation

- Docstrings of the module `commons.users.login_tokens`, `SMTPLoginTokenSender`, `LoginTokenMail`, `LoginTokenSettings` and `SMTPSettings` with the TOML example (Strato) and the wiring into `LoginTokenService` / pyhx `EmailTokenLogin`. **R18**
- Proof: `poetry run poe check` and `poetry run poe docs-build` pass.

## Risks

- **Real delivery through Strato is untested (F5):** the stand-in proves the protocol calls, not that Strato accepts them. Handled by the first deployment of casesight; the developer is told.
- **Behaviour of `smtplib` differs from the stand-in:** the stand-in mirrors the `smtplib` API used (`starttls`, `login`, `send_message`, context manager) and raises its real exception types.

## Proof per requirement

| Requirement | Proven by |
| --- | --- |
| R1, R2, R3, R4 | Step 1, `test_smtp_settings.py` |
| R5–R15 | Step 2, `test_smtp_login_token_sender.py` |
| R16 | Step 2, existing tests green, no change in `pyproject.toml` dependencies |
| R17 | Steps 1 and 2 |
| R18 | Step 3, `poe check`, `poe docs-build` |
