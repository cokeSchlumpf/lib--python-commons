# T-007 User language

## Problem

Apps built on commons and pyhx are becoming multilingual (T-003 of `app--casesight`, T-004 of `pyhx`): the language of a request is taken from the session, then from the language the user chose, then from the browser. commons has nowhere to store the language a user chose: `RegisteredUser` has no such field, and existing users tables are never migrated. Login mails of `SMTPLoginTokenSender` are written in one language chosen when the sender is created (`"en"` or `"de"`), so a user who works in Italian or French gets an English or German mail, and an app can't send each user a mail in their own language without writing its own mail function.

## Proposed outcome

- A registered user has an optional language (`RegisteredUser.locale`), empty for users who never chose one.
- Existing users tables get the new column on startup, without data loss, on SQLite and Azure SQL; databases of earlier commons versions keep working.
- Login mails are written per message in the language the message names (pyhx passes the language for the requesting user), else in the language of the sender; the built-in texts cover English, German, Italian and French.
- The API reference (docstrings) describes the user language, the migration and the mail language.
- Not part of this change: further user preferences (timezone, theme), language-specific custom templates in `app.login_tokens`, resolving the language of a request (pyhx).

## Affected users and systems

- **Apps using `SQLUsersRepository`:** their users table gets a nullable column `locale` on the first start with this version.
- **Apps using `SMTPLoginTokenSender`:** mails follow the language of each message when one is given; without one, nothing changes.
- **pyhx (T-004):** reads `RegisteredUser.locale`, stores it when a user switches the language, and passes the language to `LoginTokenService.request_login`.

## Constraints

- Backwards compatible within `versions/1` (a `feat`, minor release): existing calls, settings and stored data keep working.
- Schema evolution without Alembic: `create_all` plus ordered, idempotent migrations on startup (standard of Python web apps).
- Derived from the accepted spec of T-003 of `app--casesight` (requirements R17, R18, R30): [spec](https://github.com/cokeSchlumpf/app--casesight/blob/feature/multilingual-app/changes/02--open/T-003--multilingual-app/spec.md); its acceptance was delegated by the developer as long as this change stays within it.

## Open questions

None.
