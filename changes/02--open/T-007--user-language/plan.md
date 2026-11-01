# T-007 User language: plan

## Findings while planning

- **F1** The users table is `registered_users`; `SQLUsersRepository.__init__` calls `SQLModel.metadata.create_all(checkfirst=True)` and syncs default roles; there is no migration code yet.
- **F2** `LoginTokenMessage` is built in `LoginTokenService.request_login`; `SMTPLoginTokenSender` validates `language` against `_BUILT_IN` and passes it to `_TemplateMail`.

Deviations from the spec:

- None.

## Branching

Branch `feature/user-language`, draft PR `feat: store the user's language and send login mails in it (T-007)`. Executed by the agent as part of T-003 of `app--casesight` without review pauses per step; the developer reviews and merges the PR, the agent then merges the Release PR (1.4.0).

## Steps

### 1. User language, migration, mails per language, docstrings

- `RegisteredUser.locale`, `create(locale=…)`, `_migrate()` with `_add_users_locale`. **R1, R2**
- `LoginTokenMessage.locale`, `request_login(locale=…)`, it and fr texts, per-message language. **R3, R4, R5**
- Docstrings of `user.py`, `sql.py`, `login_tokens` and `smtp.py`. **R6**
- Proof: tests for a new database; an existing SQLite database with the 1.3.0 `registered_users` table (no `locale`) keeps its rows and gets the column; a second run is a no-op; the compiled statement for the mssql dialect; `upsert_user` stores and keeps `locale`; one mail per built-in language; `"de-CH"` → German; unknown and missing language → sender's language; custom templates still apply; `request_login` passes `locale`. `poetry run poe check` and `poetry run poe docs-build` green.

## Risks

- **Migration on Azure SQL:** covered by the compiled statement test; the real run is checked in UAT of CaseSight.

## Proof per requirement

| Requirement | Proven by |
| --- | --- |
| R1 | Step 1: `create`/`upsert_user` tests |
| R2 | Step 1: migration tests (existing table, idempotence, mssql statement) |
| R3 | Step 1: `request_login` test |
| R4 | Step 1: mails per built-in language |
| R5 | Step 1: per-message language and fallback tests, custom templates |
| R6 | Step 1: docstrings, `docs-build` |
