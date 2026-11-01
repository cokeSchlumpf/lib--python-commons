# T-004 Hashed passwords and safe role checks: plan

## Findings while planning

- **F1** The stashed port of `f03f548` (`stash@{0}`) applies cleanly on the branch. Its test `test_standard_user_requires_password_or_hash` expects a user with neither `password` nor `password_hash` to be rejected ("exactly one"), which R1 turns around; step 1 replaces it with a test that such a user has no password, and the other "exactly one" test checks for "both" instead.
- **F2** Modules of commons log through a module constant `LOG = logging.getLogger(__name__)` (`settings.py`, `events/*`, `login_tokens/sender.py`), not a shared `commons.users` logger as the spec's design says; the warnings of R13 and the log line of R18 follow that convention.
- **F3** `poe check` runs ruff, ruff format and mypy on `src/commons` and `src/jobs`, then pytest; the baseline on `main` is green (412 tests).
- **F4** No app configures roles for its settings users (`[[app.users]]` without `roles`), so R12 (unknown role raises) can't break a start. Default roles are synced in `SQLUsersRepository.__init__`, before an app calls `init_from_settings()`, so settings users can be assigned default roles.
- **F5** SQLite's `LIKE` ignores ASCII case; for `list_assignments()` and `remove_assignments()` that doesn't matter, as only normalized, lowercase paths are stored (R9).
- **F6** `tests/test_login_tokens.py` has fixtures for users, store, sender and clock; the email sign-in test of R4 reuses them.
- **F7** `RegisteredUser.create()` is called in commons by `init_from_settings()`, `update_password()`, the module docstring and tests; no caller outside commons reads `password_hash`, so making it optional (R4) only affects commons.
- **F8** (step 2) `RoleAssignmentConfig` lives in `commons.settings`, which `commons.users` imports; its validator imports `_normalize_path` inside the function, as a module-level import would be circular.
- **F9** (step 4) `upsert_role()` failed on `main` already for a role that mixes stored and new permissions (`UNIQUE constraint failed: permissions.name`): adding the new permission cascaded to the role, and the merge inserted its stored permissions again. Default roles put permissions into the database first, so the tests hit it; `upsert_role()` now builds the role in the session like the default role sync, without merging the given objects.

Deviations from the spec:

- **D1** The log calls use the module loggers `commons.users.repository` and `commons.users.sql` (F2) instead of one logger `commons.users`.

## Branching

Branch `feature/passwords-and-role-checks`, draft PR #25. One commit per step, each with a message ending in `(T-004)`; implementation pauses for a review after each step, and the PR description lists the steps done.

## Steps

### 1. Passwords and users without a password

- Apply `stash@{0}` (the port of `f03f548`: `StandardUser.password_hash`, `python -m commons.users hash-password`, `init_from_settings()` creating only new users, docstrings, `tests/test_users_settings.py`). **R2, R3, R6**
- On top: `StandardUser` allows neither (rejects only both); `RegisteredUser.password_hash` is `str | None` with a nullable column; `authenticate()` returns `None` without a hash; `hash_password("")` and `update_password(user, "")` raise `ValueError`; `init_from_settings()` stores `None` for a user with neither. **R1, R3, R4, R5**
- Drop the `stash@{0}` entry once applied and committed.
- Proof: `tests/test_users_settings.py` (port tests, F1 changes, new tests for neither, empty passwords and `authenticate()` without a hash); a test in `tests/test_login_tokens.py` that a user without a password signs in with an email link and with an email code; `poe check`.

### 2. Path normalization and containment

- `_normalize_path()` in `user.py`, used by `Role.create()`, `upsert_role()`, `add_assignment()`, `has_permission()`, `check_permission()`, `role_has_permission()`, the field validators of `DefaultRoleAssignment`, `RoleAssignmentConfig`, `Scope` and `Permission`; `_contains()` replaces `PurePosixPath.is_relative_to`. **R7, R8, R9, R10**
- Proof: new `tests/test_users_roles.py` with the examples of R7 and R8 (parametrized), the `..` bypass of the intent, an assignment in one spelling checked in another, containment (`/app/tenants/a` vs `/app/tenants/ab`, root `/`), settings with an unnormalized scope; `poe check`.

### 3. Assignments

- Unique constraint on (user, scope, role); `add_assignment()` idempotent and rejecting unknown roles; `has_permission()` compares the scope first and skips unresolvable roles with a warning; `list_assignments(scope)` and `remove_assignments(scope)` on `UsersRepository` and `SQLUsersRepository`. **R11, R12, R13, R14, R15**
- Proof: `tests/test_users_roles.py`, run with foreign keys off and on (parametrized engine fixture): duplicate assignment returns the first, admin on `/app` and on `/app/foo/bar` are two assignments, unknown role raises and writes nothing, a stale assignment is skipped with a warning (`caplog`) and others still count, listing and removing a tenant subtree (not its parent, not a sibling `…/ab`); `poe check`.

### 4. Default roles

- `Role.is_default_role`; `_sync_default_roles()` in `SQLUsersRepository.__init__` (upsert with the permissions of the code, code wins on a name clash, delete removed default roles with their assignments, one retry on `IntegrityError`); `upsert_role()` and `delete_role()` reject default roles; `list_roles()` includes them. **R16, R17, R18, R19, R20, R21**
- Proof: `tests/test_users_roles.py`, foreign keys off and on: a default role is assigned with foreign keys on (the intent's `IntegrityError` case), permissions follow the code across two repository instances on one database, a removed default role is deleted with its assignments while an app role stays, a name clash is taken over with its assignments, `is_default_role` is set on roles from memory and from the database, `upsert_role()` and `delete_role()` raise; `poe check`.

### 5. Documentation

- Docstrings of the `commons.users` module, `Role`, `Scope`, `Permission`, `RoleAssignment`, `RegisteredUser`, `UsersRepository` and `SQLUsersRepository`: path normalization (and to build scopes from generated ids), default roles, users without a password; examples with normalized paths. **R23**
- The section "Behaviour changes" for the PR description (old local databases, stricter checks, `init_from_settings()`), used by `close-change`.
- Proof: `poe check` and `poe docs-build`; a read of the rendered `docs/api/users.md` page.

## Risks

- **Port and deviation mix up (step 1):** the port is committed together with its deviations; the step report lists every line that differs from `f03f548`, so R6 can be reviewed.
- **SQLModel and SQLAlchemy details (steps 3, 4):** a `UniqueConstraint` in `__table_args__`, merging a `Role` with its permission relationship, and `selectinload` before detaching may behave differently than expected; the tests run against real SQLite databases, with foreign keys on and off.
- **Type change of `password_hash` (step 1):** mypy flags callers in commons that assume `str`; consumers outside commons don't read it (F7).
- **Parallel starts (step 4):** the retry is tested by a sync against a database that already holds the rows, not by real parallel processes (spec, Areas of concern 7).
- **Old local databases (steps 3, 4):** they fail with "no such column" after the upgrade; documented in step 5 (spec, Areas of concern 1).

## Proof per requirement

| Requirement | Proven by |
| --- | --- |
| R1 | Step 1: settings tests for neither and for both |
| R2 | Step 1: CLI tests of the port (stdin, prompt twice, mismatch) and empty password |
| R3 | Step 1: `init_from_settings()` tests (plain, hash, neither, existing user untouched) |
| R4 | Step 1: `authenticate()` without a hash; email link and code sign-in in `test_login_tokens.py` |
| R5 | Step 1: `hash_password("")` and `update_password(user, "")` raise |
| R6 | Step 1: port tests unchanged except F1; step report lists the differences to `f03f548` |
| R7 | Step 2: parametrized normalization examples |
| R8 | Step 2: `.`, `..`, empty segment, `""` and `//` raise |
| R9 | Step 2: every entry point with an unnormalized path; assignment in one spelling, check in another |
| R10 | Step 2: containment tests (`/`, sub-scope, `…/ab`) |
| R11 | Step 3: duplicate and sub-scope assignment tests |
| R12 | Step 3: unknown role raises, no row written |
| R13 | Step 3: stale assignment skipped, warning logged, other assignments count |
| R14 | Step 3: listing a tenant subtree |
| R15 | Step 3: removing a tenant subtree, return value, scope rows |
| R16 | Step 4: `is_default_role` from memory and from the database |
| R17 | Step 4: sync of permissions; name clash taken over |
| R18 | Step 4: removed default role deleted with its assignments |
| R19 | Step 4: app role untouched by the sync |
| R20 | Step 4: `upsert_role()` and `delete_role()` raise for default roles |
| R21 | Step 4: `list_roles()` includes default roles |
| R22 | Steps 1–4: tests as listed, role parts with foreign keys off and on |
| R23 | Step 5: docstrings, `poe check`, `poe docs-build` |
