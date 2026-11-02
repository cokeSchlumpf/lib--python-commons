# T-009 User access period: plan

## Findings while planning

- **F1** `commons.database.types.UTCDateTime` can't be used in `commons.users.user`: `commons.database` imports `commons.users` (circular import). The columns are plain `DateTime` holding naive UTC; the properties return aware UTC values.
- **F3** `check_permission` raises `LookupError`, not `PermissionError`.
- **F2** pyhx checks only `result.ok` after redeeming and shows the same page for every request status, so new enum values need no change there.

Deviations from the spec:

- **D1** Columns are `DateTime` with naive UTC instead of `UTCDateTime` (F1); the behaviour of R1 is the same.

## Branching

Branch `feature/user-access-period`, draft PR #41. The developer authorized running the steps without review stops (as part of T-008 of `app--casesight`); the developer reviews and merges the PR and the Release PR.

## Steps

### 1. Access period, sign-in, permissions and listing

- `RegisteredUser` fields and `can_sign_in`; `authenticate`, `registered_user_has_permission`, `request_login`, `_redeem`; `list_users`; docstrings. **R1–R9**
- Proof: new `tests/test_users_access_period.py` (R10) and `poe check`.

## Risks

- **Old databases** (concern 1 of the spec): documented; no code can prevent it without migrations.

## Proof per requirement

| Requirement | Proven by |
| --- | --- |
| R1, R2 | Step 1, tests of fields and bounds |
| R3 | Step 1, tests of permissions with assignment and default permission |
| R4 | Step 1, password login test |
| R5, R6 | Step 1, login token tests |
| R7 | Step 1, listing test |
| R8, R9 | Step 1, existing tests unchanged; docstrings reviewed |
| R10 | Step 1 |
