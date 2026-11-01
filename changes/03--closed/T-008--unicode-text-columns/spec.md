# T-008 Unicode text columns on Azure SQL: spec

## Requirements

- **R1** `commons.database` exports `UnicodeCode` and `UnicodeName`: column types for `Field(sa_type=…)` that create `NVARCHAR(64)` and `NVARCHAR(255)` on SQL Server and a `VARCHAR` of the same length elsewhere; they are usable in a fields class shared by a live and a history table.
- **R2** `HistoryMixin.history_changed_by_user_displayname` is `NVARCHAR(255)` on SQL Server.
- **R3** `registered_users.display_name` (`NVARCHAR(128)`), `firstname` and `lastname` (`NVARCHAR(64)`) are Unicode on SQL Server; all other columns of `commons` keep their types.
- **R4** Names with characters outside code page 1252 round-trip unchanged (tested on SQLite; SQL Server only by its DDL).
- **R5** The docstring of `commons.database` (rendered in the API docs) says when to use `VARCHAR` and when `NVARCHAR`, and how to convert existing tables with `ALTER TABLE … ALTER COLUMN … NVARCHAR(n)`.
- **R6** Python types, signatures and behaviour on SQLite don't change; `poe check` and `poe docs-build` pass.

## Design

In `database/types.py`, next to `EnumString`:

```python
class UnicodeCode(TypeDecorator[str]):
    impl = Unicode(CODE_LENGTH)
    cache_ok = True


class UnicodeName(TypeDecorator[str]):
    impl = Unicode(NAME_LENGTH)
    cache_ok = True
```

`HistoryMixin`: `Field(sa_type=UnicodeName)` instead of `max_length=NAME_LENGTH`. `RegisteredUser`: `Column("display_name", Unicode(128))` and so on, keeping the lengths of the table. `Unicode(n)` is `VARCHAR(n)` on SQLite and PostgreSQL, so only SQL Server changes.

## Alternatives considered

- **`sa_type=Unicode` with `max_length`:** SQLModel ignores the length and creates `NVARCHAR(max)`, which can't be indexed.
- **A Unicode collation on Azure SQL (`…_UTF8`):** would make `VARCHAR` store UTF-8, but is a database setting of each deployment, not of the library, and changes byte lengths of indexes.
- **Migrating existing tables in `commons`:** there is no migration mechanism in `commons`; each app owns its schema evolution.

## Constraint mapping

| Constraint (intent) | Met by |
| --- | --- |
| Backwards compatible, minor release | R6; additions and DDL types only |
| Indexes below 1700 bytes | R1 (`NVARCHAR(255)` = 510 bytes) |

## Open questions

None.

## Areas of concern

1. **Existing Azure SQL tables keep `VARCHAR`** (R3, R5): apps keep losing characters until they convert; the docs show how. Owner: Michael Wellner.

## Out of scope

- Usernames, e-mail addresses, role, scope and permission names, the key of events, login tokens.
- Migrating existing tables; changing the apps.

## Outcome

Implemented as specified, with these deviations and findings (from the plan, removed at close-out):

- **D1** Implemented in pull request #38, which started as the backlog item on the branch `docs/unicode-text-columns`; the branch keeps its name, the title of the pull request became `feat(database): …`.
- **F1** `commons.database` is documented by its module docstring; the guidance on `VARCHAR` and `NVARCHAR` and the `ALTER TABLE` example are there.
- **F2** `Unicode(n)` creates `VARCHAR(n)` on SQLite, so nothing changes there; the tests check the DDL of SQL Server by compiling it with the MSSQL dialect and the round trip on SQLite.

Rollout: released with the next minor version of `versions/1` after the merge of pull request #38. Apps get `NVARCHAR` for these columns in new tables; existing tables on Azure SQL keep `VARCHAR` until the app converts them.

Open after this change:

- app--casesight replaces its own `UnicodeCode` / `UnicodeName` (`adapters/sql/cases_repository/_columns.py`) with the ones of `commons` once released. Owner: Michael Wellner.
- Apps already on Azure SQL convert `registered_users` and their history tables (`ALTER TABLE`, see the docs). Owner: the owner of each app.
