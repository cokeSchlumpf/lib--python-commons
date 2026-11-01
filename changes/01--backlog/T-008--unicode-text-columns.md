# T-008 Unicode text columns on Azure SQL

## Problem

SQLModel creates `str` columns as `VARCHAR(n)` on Azure SQL (checked by compiling `CREATE TABLE` with the MSSQL dialect in app--casesight T-004). With the default collation of Azure SQL (`SQL_Latin1_General_CP1_CI_AS`, code page 1252), German umlauts survive, but other characters, e.g. `ł`, `ş`, `ő`, Cyrillic, Greek or emoji, are stored as `?`. That is silent data loss in every text column of `commons` and of the apps that holds names or free text: in `commons` e.g. `history_changed_by_user_displayname` of `HistoryMixin`, the names in the users table, and `key` of the events table. Locally nobody notices, as SQLite stores any Unicode.

`sa_type=Unicode` doesn't help: SQLModel then ignores `max_length` and creates `NVARCHAR(max)`, which can't carry an index or a unique constraint. A `TypeDecorator` with `impl = Unicode(n)` (as `EnumString` does for `String`) gives `NVARCHAR(n)` and works in fields classes shared by a live and a history table; app--casesight T-004 defines such types in the app for now.

## Proposed outcome

- `commons.database` offers length-bounded Unicode column types for text that users enter (e.g. for `NAME_LENGTH` and `CODE_LENGTH`), next to `EnumString`, documented with when to use `VARCHAR` (ASCII keys, IDs) and when `NVARCHAR`.
- The text columns of `commons` that hold names or free text (`HistoryMixin`, users, possibly events) use them; how existing Azure SQL tables are migrated (or not) is decided in the spec.
- The apps can replace their own Unicode types with the ones of `commons`.
