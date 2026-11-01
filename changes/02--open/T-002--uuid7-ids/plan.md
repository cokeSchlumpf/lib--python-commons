# T-002 Time-ordered UUIDv7 ids: plan

## Findings while planning

- **F1** The default at `user.py` line 275 belongs to `AuthenticatedUser.id_` (`User` is a `Protocol` without a default); line 350 is `AuthenticatedUser`'s factory, line 774 `RegisteredUser`'s, lines 567 and 644 the defaults of `RoleAssignment.id` and `RegisteredUser.id_`. The spec's "`User.id_`" means `AuthenticatedUser.id_`.
- **F2** No test covers the generated ids of `EntityMixin`, the users, role assignments or jobs today, and `jobs` has no tests at all; `SQLJobsRepository(engine)` on SQLite can create a job for one.
- **F3** `tests/test_login_tokens.py` checks that a request id exists, not its form; R7 needs a test of its own.

Deviations from the spec:

- None.

## Branching

Branch `feature/uuid7-ids`, draft PR #20 (`feat: Generate time-ordered UUIDv7 ids`). One commit per step; implementation pauses for a review after each step.

## Steps

### 1. `new_id`

- `src/commons/id_operators.py` with `new_id()`; re-exported in `commons/database/__init__.py` (and `__all__`); `id_operators` listed in `commons/__init__.py` like the other operator modules. **R1, R2**
- Proof: `tests/test_id_operators.py`: a 36-character UUID of version 7; 1,000 ids in a row are unique and sorted; `commons.database.new_id is commons.id_operators.new_id`; importing `commons.users` first and `commons.database` first each succeed in a fresh interpreter (`subprocess`, `sys.executable -c ...`).

### 2. Ids from `new_id`

- `EntityMixin.id`, `AuthenticatedUser.id_`, `RoleAssignment.id`, `RegisteredUser.id_` default to `new_id`; the two factories use `id or new_id()`; `JobsRepositoryPort.create` uses `new_id()`; `Event.event_id` defaults to `new_id` and `_new_event_id` is removed; no unused `uuid4` import left. Login tokens untouched. **R3, R4, R5, R6, R7, R8**
- Proof: `tests/test_new_ids.py`: for an `EntityMixin` table, `AuthenticatedUser`, both factories, `RoleAssignment`, `RegisteredUser`, a job created by `SQLJobsRepository` on SQLite, and an `Event`: the generated id is a version-7 UUID, and an id passed in explicitly is kept; a login request id (real, unknown address, rate-limited) is still 32 hex characters of a version-4 UUID. The existing tests (users, login tokens, events) pass unchanged (R8).

### 3. Documentation

- `docs/api/id-operators.md` (`::: commons.id_operators`) in the "General" section of `mkdocs.yml`; the comment in `column_lengths.py` names UUIDv7 for new ids. **R9**
- Proof: `poetry run poe docs-build` (strict) and `poetry run poe check` pass; `grep -rn uuid4 src` shows only `login_tokens/service.py`.

## Risks

- **Import cycle shows up only in one import order:** step 1 tests both orders in fresh interpreters, where nothing is imported yet.
- **Apps used ids as secrets:** not in `commons` (checked: only login request ids are handles, R7); named in the PR description for apps.

## Proof per requirement

| Requirement | Proven by |
| --- | --- |
| R1 | Step 1, `test_id_operators.py` |
| R2 | Step 1, `test_id_operators.py` (re-export, both import orders) |
| R3 | Step 2, `test_new_ids.py` |
| R4 | Step 2, `test_new_ids.py` |
| R5 | Step 2, `test_new_ids.py` |
| R6 | Step 2, `test_new_ids.py` and `test_events_event.py` |
| R7 | Step 2, `test_new_ids.py` |
| R8 | Step 2, existing tests unchanged; no column changes in the diff |
| R9 | Step 3, `poe docs-build`, `poe check`, `grep` |
