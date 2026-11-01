# T-007 User language: spec

## Requirements

### User language

- **R1** `RegisteredUser` has `locale: str | None` (a language tag such as `"de"` or `"de-CH"`, at most 35 characters), `None` by default; `RegisteredUser.create(…, locale=…)` accepts it and `upsert_user` stores it. (T-003 R17)
- **R2** `SQLUsersRepository` adds the column `locale` to an existing `registered_users` table that lacks it when it is created, on SQLite and Azure SQL (mssql); existing rows keep their data and get `NULL`; running it again changes nothing. (T-003 R17)

### Login mails per language

- **R3** `LoginTokenMessage` has `locale: str | None = None`; `LoginTokenService.request_login(…, locale=None)` puts it into the message it sends. (T-003 R18)
- **R4** The built-in subject and text of `SMTPLoginTokenSender` exist for `"en"`, `"de"`, `"it"` and `"fr"`; the `language` argument accepts all four. (T-003 R18)
- **R5** The default mail function writes each mail in the language of `message.locale` (its language part, e.g. `"de"` of `"de-CH"`) when built in, else in the sender's `language`. Templates set in `app.login_tokens` apply to every language, as today. (T-003 R18)

### Documentation

- **R6** The docstrings, from which the API reference is generated, describe `RegisteredUser.locale`, the migration of existing users tables (replacing the note that existing tables are not migrated) and the language per mail (replacing the hint to pass an own mail function for a language per user). (T-003 R30)

## Design

- `RegisteredUser.locale: str | None = Field(default=None, max_length=35)`; `create()` gets the keyword.
- `SQLUsersRepository.__init__`: after `create_all`, `_migrate()` runs an ordered list of idempotent steps; the first, `_add_users_locale`, inspects `registered_users` (`sqlalchemy.inspect(engine).get_columns`) and, if `locale` is missing, runs `ALTER TABLE registered_users ADD locale <type> NULL`, the type compiled for the engine's dialect (`String(35).compile(dialect=engine.dialect)`). `ADD` without `COLUMN` is valid in SQLite and T-SQL.
- `LoginTokenMessage` (dataclass) gets `locale: str | None = None` as the last field; `request_login` gets the keyword-only `locale` and passes it.
- `Language = Literal["en", "de", "it", "fr"]`; `_BUILT_IN` gets it and fr. `_TemplateMail` builds one `(subject, text)` template pair per built-in language (settings templates override all of them) and picks the pair for `message.locale`'s language part, else the sender's.

## Alternatives considered

- **A `user_preferences` table:** more general, but an extra lookup per request and nothing else to store yet.
- **The mail language only from `message.user.locale`:** would ignore the language the login page was shown in; pyhx resolves it (session, user, browser) and passes it.
- **Alembic:** not used by the platform; the standard is `create_all` plus idempotent steps.

## Constraint mapping

| Constraint (intent) | Met by |
| --- | --- |
| Backwards compatible within `versions/1` | R1 (nullable, default `None`), R2 (migration), R3 (new keyword and field with defaults), R4/R5 (`language` still applies) |
| `create_all` plus idempotent migrations | R2 |
| Within the spec of T-003 | R1–R6 map to T-003 R17, R18, R30 |

## Open questions

None.

## Areas of concern

1. **The first migration runs on every app's database** (R2): tested on SQLite with a table of the 1.3.0 schema and by compiling the mssql statement; the real Azure SQL run happens with the CaseSight release in UAT. Owner: agent; UAT check: developer.

## Out of scope

- Further user preferences, language-specific custom templates in `app.login_tokens`, resolving the language of a request (pyhx T-004).

## Outcome

Implemented as specified, with these deviations and findings (from the plan, removed at close-out):

- **F1** `UsersRepository.update_password` rebuilt the user without the new field and would have reset `locale` on every password change; it now keeps it (tested).
- **F2** `RegisteredUser.locale` is a property with a setter (the other fields are read-only properties), so callers such as pyhx can change the language of a loaded user and save it with `upsert_user`.
- **F3** The migration statement is built by `_add_users_locale_statement(dialect)` and tested for SQLite and mssql; the existing test that used `"fr"` as an unknown mail language now uses `"es"`.

Rollout: PR #35, released as commons 1.4.0 on `versions/1` after the developer's review and merge.

Open after this change: the first run of the migration on Azure SQL happens with the CaseSight release of T-003 in UAT (developer checks it); pyhx T-004 uses the user language and passes the mail language.
