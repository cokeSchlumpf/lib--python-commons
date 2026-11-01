# T-008 Unicode text columns on Azure SQL

## Problem

SQLModel creates `str` columns as `VARCHAR(n)` on Azure SQL (checked by compiling `CREATE TABLE` with the MSSQL dialect in app--casesight T-004). With the default collation of Azure SQL (`SQL_Latin1_General_CP1_CI_AS`, code page 1252), German umlauts survive, but other characters, e.g. `ł`, `ş`, `ő`, Cyrillic, Greek or emoji, are stored as `?`. That is silent data loss in every text column of `commons` and of the apps that holds names or free text, e.g. `history_changed_by_user_displayname` of `HistoryMixin` and the names in the users table. Locally nobody notices, as SQLite stores any Unicode.

`sa_type=Unicode` doesn't help: SQLModel then ignores `max_length` and creates `NVARCHAR(max)`, which can't carry an index or a unique constraint. A `TypeDecorator` with `impl = Unicode(n)` (as `EnumString` does for `String`) gives `NVARCHAR(n)` and works in fields classes shared by a live and a history table; app--casesight T-004 defines such types in the app for now.

## Proposed outcome

- `commons.database` offers length-bounded Unicode column types for text that people enter, `UnicodeCode` (`CODE_LENGTH`) and `UnicodeName` (`NAME_LENGTH`), next to `EnumString`, documented with when to use `VARCHAR` (ASCII: ids, codes, hashes, e-mail addresses, URLs) and when `NVARCHAR` (names and free text).
- The name columns of `commons` use `NVARCHAR`: `history_changed_by_user_displayname` of `HistoryMixin`, and `display_name`, `firstname`, `lastname` of the users table.
- Existing tables are not migrated: `create_all` doesn't change them, and writing to a `VARCHAR` column keeps working as before (with the same loss). The documentation shows the `ALTER TABLE` statements an app runs to convert them.
- The apps can replace their own Unicode types with the ones of `commons` (app--casesight, separately).
- Not part of this change: other columns (usernames, role and scope names, the key of events), migrations, the apps.

## Affected users and systems

- **Apps on Azure SQL:** new tables get `NVARCHAR` for these columns; existing tables stay until converted.
- **`commons.database`, `commons.users`:** new types, changed column types; tests and API docs.

## Constraints

- Backwards compatible, a minor release of `versions/1`: no change of Python types or signatures; SQLite and other databases behave as before.
- Indexes stay below the 1700 byte key limit of SQL Server (`NVARCHAR(255)` is 510 bytes).

## Open questions

None. The developer asked to implement it right away in pull request #38.
