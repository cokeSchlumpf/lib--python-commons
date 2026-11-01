# T-008 Unicode text columns on Azure SQL: plan

## Findings while planning

- **F1** `commons.database` is documented by its module docstring (`docs/api/database.md` is `::: commons.database`).
- **F2** `RegisteredUser` defines its columns with `sa_column=Column(…, String(n))`, so its names change to `Unicode(n)` there; `HistoryMixin` uses `Field(max_length=NAME_LENGTH)`.
- **F3** `poe check` passes with 641 tests before the change.

Deviations from the spec:

- None.

## Branching

Branch `docs/unicode-text-columns` of pull request #38, which started as the backlog item; its title becomes `feat(database): Unicode text columns on Azure SQL (T-008)`. The developer asked to implement it in one go and reviews the finished pull request.

## Steps

### 1. Types, columns, docs

- `UnicodeCode`, `UnicodeName`, exported; `HistoryMixin` and `RegisteredUser` changed; module docstring. **R1 to R5**
- Proof: `tests/test_database_unicode_columns.py`: DDL compiled for MSSQL (new types, history mixin in a shared fields class, users table, other columns unchanged), DDL on SQLite unchanged, round trip of `Łucja Wąs-Müller` through a history table and the users table on SQLite; `poe check`, `poe docs-build`. **R6**

## Risks

- **Only DDL is checked for SQL Server:** no test runs against Azure SQL.

## Proof per requirement

| Requirement | Proven by |
| --- | --- |
| R1 to R4 | Step 1, `test_database_unicode_columns.py` |
| R5 | Step 1, docstring, `poe docs-build` |
| R6 | Step 1, `poe check` (all existing tests) |
