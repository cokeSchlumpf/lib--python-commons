# T-004 Hashed passwords and safe role checks: spec

## Requirements

### Users in the settings and passwords

- **R1** A user in the settings (`StandardUser`) has `password`, `password_hash` or neither; a user with both is rejected with a validation error when the settings are read.
- **R2** `python -m commons.users hash-password` prompts for a password twice without echo and prints its bcrypt hash; with `--stdin` it reads the password from stdin (without the trailing line break). Different inputs or an empty password end with a non-zero exit code; the plain-text password is never printed.
- **R3** `init_from_settings()` creates only users whose username doesn't exist yet, with their configured roles; for existing users it changes nothing (password, names, roles). A configured `password` is hashed, a `password_hash` is stored as given, and a user with neither has no password.
- **R4** A `RegisteredUser` can have no password. `authenticate()` returns `None` for a user without a password, whatever password is entered. Sign-in with an email link or code (`commons.users.login_tokens`) works for them as for any other user with an email address.
- **R5** `hash_password("")` and `update_password(user, "")` raise `ValueError`; an empty password is never stored as a usable password.
- **R6** Apart from R1 (neither), R4 and R5, this part matches `kpmg--lib--commons` commit `f03f548`: code, docstrings and tests.

### Scope and permission paths

- **R7** Every scope and permission path is normalized to one canonical spelling: segments are separated by `/`; empty segments (leading, trailing and double slashes) are dropped and a leading `/` is added; in each segment, accents are removed, letters are lowercased, and every run of characters other than `a–z`, `0–9` and `-` becomes one `-`, without leading or trailing `-`. Dashes already in a segment stay, so double dashes are kept. Examples: `/app/` and `app` → `/app`; `/app//x` → `/app/x`; `/foo/Foo Bar` → `/foo/foo-bar`; `/lib--python-commons` stays; an uppercase UUID is lowercased.
- **R8** Normalizing never changes which scope is meant, so these raise `ValueError` instead: a segment `.` or `..`; a segment that is empty after normalizing (`/ `, `/!!!`); and a path without any segment other than the literal `/` (`""`, `//`), as only `/` means the root.
- **R9** Paths are normalized where they enter, and only normalized paths are stored, compared and returned: `Role.create()`, `upsert_role()`, `add_assignment()`, `DefaultRoleAssignment`, `RoleAssignmentConfig` (when the settings are read), `has_permission()`, `check_permission()`, `role_has_permission()`, and listing and removing by scope (R14, R15). Two spellings of one path behave alike everywhere: `has_permission(user, "/App/", "/Read")` is the same check as `has_permission(user, "/app", "/read")`.
- **R10** A scope contains itself and every scope below it, segment by segment: `/` contains every scope, `/app/tenants/a` contains `/app/tenants/a/x` but not `/app/tenants/ab`. Permissions are contained the same way.

### Role assignments

- **R11** A user has a role on a scope at most once: the database holds at most one assignment per (user, scope, role), and `add_assignment()` for an existing one, in any spelling of the scope, returns it without writing a second one. Assignments that differ in scope or role are separate, also when one scope lies below the other: a user can be admin on `/app` and on `/app/foo/bar`, and keeps the latter when the former is removed.
- **R12** `add_assignment()` with a role that exists neither in `default_roles` nor in the database raises `KeyError` and writes nothing.
- **R13** `has_permission()` never raises because a role of an assignment or of a default permission entry can't be found: it skips that entry, logs a warning, and decides on the remaining entries.
- **R14** `list_assignments(scope)` returns the assignments on that scope and the scopes below it, each with its user, role and scope loaded; assignments on scopes above it are not included.
- **R15** `remove_assignments(scope)` removes the assignments on that scope and the scopes below it, and the scope entries left without assignments; it returns how many assignments it removed.

### Default roles

- **R16** Every `Role` tells whether it is a default role (`Role.is_default_role`), both when it comes from the database (`list_roles()`, `find_role_by_name()`, assignments) and from `default_roles`, so an app can show default roles as not editable.
- **R17** When a `SQLUsersRepository` is created, every role in `default_roles` is in the database, marked as default role, with exactly the permissions given in the code. If a role created by the app has the same name, the code wins: the role is marked as default role, gets the permissions of the code, and keeps its assignments.
- **R18** When a `SQLUsersRepository` is created, every role marked as default role that is no longer in `default_roles` is deleted, together with its assignments.
- **R19** Apart from R17 (same name), the sync doesn't change or delete roles that aren't marked as default roles.
- **R20** `upsert_role()` and `delete_role()` raise `ValueError` for a default role (by name, or marked as default role); default roles change only through the code.
- **R21** `list_roles()` includes the default roles.

### Tests and documentation

- **R22** Tests cover R1–R21 on SQLite, the role and permission parts with foreign keys both off and on (`PRAGMA foreign_keys=ON`), including the cases of the intent: the `..` path, duplicate assignments, the same role on a scope and on a scope below it, an unknown role, a default role that is assigned with foreign keys on, and a default role removed from the code; and the normalization examples of R7 and R8, including an assignment made in one spelling and checked in another. A test shows that a user without a password signs in with an email link and with an email code (`commons.users.login_tokens`), while `authenticate()` rejects them.
- **R23** The docstrings of `commons.users` (module, `Role`, `Scope`, `Permission`, `RoleAssignment`, `RegisteredUser`, `UsersRepository`, `SQLUsersRepository`) describe the path normalization, the default role sync and users without a password. `poe check` and `poe docs-build` pass.

## Design

Everything stays in `commons/users/` (`user.py`, `repository.py`, `sql.py`, `__main__.py`) and `commons/settings.py`; no new module, no new dependency.

### Passwords (R1–R6)

The stashed port of `f03f548` (`stash@{0}`: `settings.py`, `users/__init__.py`, `users/__main__.py`, `repository.py`, `user.py`, `tests/test_users_settings.py`) is applied first, unchanged; the deviations then go on top:

| Place | Port (`f03f548`) | After this change |
| --- | --- | --- |
| `StandardUser._check_password_or_hash` | exactly one of both | at most one of both (R1) |
| `RegisteredUser.password_hash_` | `str`, column `String(256)` | `str \| None`, nullable column; `None` means no password; `RegisteredUser.create(password_hash: str \| None, …)` keeps its positional order (R4) |
| `UsersRepository.authenticate()` | verifies against the hash | returns `None` if the user has no hash (`None` or `""`), before the verifier is called (R4) |
| `UsersRepository.hash_password()`, `update_password()` | hash any string | raise `ValueError` for `""` (R5) |
| `init_from_settings()` | `password_hash or hash_password(password or "")` | `password_hash`, else `hash_password(password)` if a password is set, else `None` (R3) |

The CLI (`__main__.py`) is taken from the port as is; it already rejects an empty password (R2). Treating `""` like `None` in `authenticate()` keeps users safe whose empty hash came from elsewhere.

### Paths (R7–R10)

One private helper in `user.py` normalizes a path or raises; it reuses `string_operators.remove_accents` (prototyped against the examples of R7 and R8):

```python
from commons.string_operators import remove_accents

def _normalize_path(kind: str, value: str) -> str:
    if value == "/":
        return "/"
    segments = []
    for raw in value.split("/"):
        if raw == "":
            continue  # leading, trailing or double slash
        if raw in (".", ".."):
            raise ValueError(f"Invalid {kind} `{value}`: `.` and `..` are not allowed.")
        segment = re.sub(r"[^a-z0-9-]+", "-", remove_accents(raw).lower()).strip("-")
        if not segment:
            raise ValueError(f"Invalid {kind} `{value}`: segment `{raw}` is empty after normalizing.")
        segments.append(segment)
    if not segments:
        raise ValueError(f"Invalid {kind} `{value}`: only `/` means the root.")
    return "/" + "/".join(segments)
```

- Every entry point of R9 passes its paths through it before anything else: `Role.create()` normalizes the permission names, `upsert_role()` normalizes the permissions of the given role, `DefaultRoleAssignment.scope` and `RoleAssignmentConfig.scope` get a Pydantic `field_validator` that returns the normalized value (plain models, where validators run). The field validators of `Scope` and `Permission` call it as well, though SQLModel doesn't run them on table models.
- Because only normalized paths are stored and compared, containment is a string comparison by segments and replaces `PurePosixPath.is_relative_to`, which doesn't resolve `..`; `_scope_contains_scope()` and `_permission_contains_permission()` use it:

```python
def _contains(allowed: str, to_check: str) -> bool:
    return allowed == "/" or to_check == allowed or to_check.startswith(allowed + "/")
```

### Assignments (R11–R15)

- `RoleAssignment` gets `UniqueConstraint("user_id", "scope_name", "role_name")`. `add_assignment()` normalizes the scope, looks for the existing row and returns it; otherwise it checks the role with `find_role_by_name()` (`KeyError` if missing) and inserts. The constraint is the safety net if two processes assign at the same time.
- `registered_user_has_permission()` and the anonymous and authenticated branches of `has_permission()` compare the scope first and resolve the role only for matching entries; an entry whose role is `None` is skipped with `logger.warning(...)` (module logger `commons.users`).
- `UsersRepository` gets two abstract methods, implemented in `SQLUsersRepository`:
  - `list_assignments(scope: str) -> list[RoleAssignment]`: `WHERE scope_name = :s OR scope_name LIKE :s || '/%'` (all rows for `/`), with `selectinload` of `user`, `role` and `scope` before the objects are detached. Normalized paths contain neither `%` nor `_`, so no escaping is needed.
  - `remove_assignments(scope: str) -> int`: deletes the same rows, then the `scopes` rows of that subtree without assignments, in one transaction.

### Default roles (R16–R21)

- `Role` gets `is_default_role: bool`, column `Boolean`, not null, default `False`; it is a public field, so apps read it from every `Role` they get (R16).
- `SQLUsersRepository.__init__` sets `is_default_role=True` on the roles in `default_roles` (so roles from memory and from the database agree) and runs `_sync_default_roles()` after `create_all`, in one transaction:
  1. for each role in `default_roles`: the permissions are inserted if missing, the role is merged by name with `is_default_role=True` and exactly the permissions of the code, whether or not a role of that name existed (R17);
  2. each role with `is_default_role=True` whose name isn't in `default_roles`: its `role_assignments` rows, its `role_permissions` rows and the role are deleted; the number of removed assignments is logged (R18). `permissions` rows stay, as other roles may share them.
- If a second process inserts the same default role at the same moment (several workers starting together), the commit fails with `IntegrityError`; the sync then runs once more, which finds the rows and only updates them.
- `find_role_by_name()` keeps looking in `default_roles` first: same content as the database, no query.
- `upsert_role()` and `delete_role()` raise `ValueError` if the name is in `default_roles` or the role is marked as default role (R20); only the sync writes default roles.

### Documentation (R23)

`docs/api/users.md` renders the module (`::: commons.users`), so the docstrings are the documentation; the module docstring gets a section on path normalization, on default roles and on users without a password, and its example uses normalized paths. The changelog comes from the PR title via release-please; the PR description lists the behaviour changes (see Areas of concern).

## Alternatives considered

- **Keep default roles in memory and drop the foreign key on `role_name`:** simplest, and a removed role would stop granting by itself; decided against in the intent: the developer wants the roles in the database, deleted when removed from the code.
- **Upgrade existing tables in place** (`ALTER TABLE roles ADD COLUMN …`, create the unique index if missing): would keep old local databases working, but is the start of a migration framework the intent excludes; no real app has data yet.
- **Reject every path that isn't canonical** (the first proposal of Q1): one spelling per scope without any conversion, and bugs in how an app builds scopes would show; decided against by the developer, as `/app/` and `/app` should mean the same.
- **Normalize with `string_operators.normalize_path` and `ensure_path_slugified`** (`path_operators` only finds directories): they collapse double dashes (`normalize_slug`), drop `..` silently (`/a/../b` becomes `/a/b`) and let dots through in the last segment (`/app/..` stays as it is). Changing them would change storage keys in `commons.storage`, app--beleglotse and app--cross-border-rules. The helper reuses `remove_accents` from there and keeps the rest of the rule in `commons.users`.
- **Resolve `.` and `..`** instead of rejecting them: `/app/tenants/a/../b` would become `/app/tenants/b`, a scope the caller may not have meant to check; rejecting shows the bug.
- **An empty string as "no password":** works without a schema change, but `""` is easy to produce by accident; `None` says it explicitly, and `""` is still treated as no password for safety.
- **Delegation in commons** (`assign(actor, …)`): out of scope by the intent; it is the app's decision.

## Constraint mapping

| Constraint (intent) | Met by |
| --- | --- |
| Minor release (`feat`, 1.2.0), behaviour changes called out | PR title `feat: …`; behaviour changes listed in the PR description (Areas of concern 4) |
| Existing `password` entries stay valid | R1, R3 |
| Hash matches the repository's verifier, CLI uses the default hasher | R2, design Passwords (`_default_hash_password`) |
| Plain-text passwords never printed or logged | R2 |
| No new dependency | Design (standard library, bcrypt, SQLAlchemy, `string_operators`) |
| No database migration | Design Default roles; Alternatives (no in-place upgrade); Areas of concern 1 |
| Invalid input rejected, never silently corrected into a different scope or a usable empty password | R5, R8, R12; R7 and R9 change only the spelling, never the scope meant (changed while specifying, see Out of scope) |

## Open questions

None.

## Areas of concern

1. **Old local databases break** (R11, R16): a database created before this change has no `is_default_role` column, and `SQLUsersRepository` fails on start with "no such column". UAT is not affected: no app deploys with the Azure SQL database, and the SQLite files there aren't on persistent storage. Handled by a note in the PR description and changelog ("delete the app's data directory"). Owner: Michael Wellner.
2. **Access revoked silently** (R18): removing a default role from the code deletes its assignments on the next start, as the developer decided; a rollback doesn't bring them back. Handled by logging the number of removed assignments. Owner: Michael Wellner.
3. **Configuration mistakes skipped quietly** (R13): an assignment to a missing role grants nothing instead of failing. Handled by a warning in the log and by R12, which prevents such assignments from being created. Owner: Michael Wellner.
4. **Release type versus the library rule** (R4, R8, R14–R16): the shared rules call a break of the public API `feat!`. This change makes `RegisteredUser.password_hash` optional, lets `has_permission()` raise `ValueError` for paths with `.`, `..` or no segment, adds abstract methods to `UsersRepository` and changes the schema. The intent decided on a minor release, as nothing uses these parts yet; the PR description lists each change under "Behaviour changes". Owner: Michael Wellner.
5. **Different ids sharing one scope** (R7): normalization maps ids that differ only in case, accents or special characters to the same scope (`Tenant_A` and `tenant-a` both become `/…/tenant-a`), so two tenants with such ids would share their roles. Ids from `new_id()` (UUIDs) are not affected. Handled by documenting it in the docstrings: scopes should be built from generated ids, not from names. Owner: the developer of each app.
6. **Planned permission checks in the apps** (R7): app--beleglotse and app--cross-border-rules have commented-out checks like `has_permission(user, "/app/admin/…", "read")`; with normalization, `read` becomes `/read` and works. Owner: the developer of each app, when the checks are enabled.
7. **Several workers starting at once** (R17, R18): the default role sync can race. Handled by the retry in the design and by the unique constraint. It isn't tested with real parallel processes. Owner: Michael Wellner.
8. **Only tested on SQLite** (R22): Azure SQL (MSSQL) enforces foreign keys and is the target for persistent apps; the tests with `PRAGMA foreign_keys=ON` stand in for it. Owner: Michael Wellner.

## Out of scope

- Changed while specifying: the intent's "invalid input is rejected, never silently corrected" now holds for `.`, `..`, empty segments and missing segments (R8); different spellings of the same path are normalized to one (R7, Q1 of the spec, answered by the developer).
- Who may assign which role (delegation): the app's job (intent).
- Migrating existing databases (intent).
- Listing users (`list_users()`), other user types, the login token flow, an async or transactional API.
- Changes in the apps, e.g. app--casesight dropping its random password hash, or pyhx's login form: they follow in their own changes.
- Encrypting other settings and a Key Vault integration (T-003).

## Outcome

Implemented as specified, with these deviations and findings (from the plan, removed at close-out):

- **D1** The log calls use the module loggers `commons.users.repository` and `commons.users.sql`, following the convention of commons (`LOG = logging.getLogger(__name__)`), instead of one logger `commons.users`.
- **F1** The port of `f03f548` had a test rejecting users with neither `password` nor `password_hash`; it was replaced by a test that such a user has no password (R1). Otherwise the port is unchanged; the deviations from `f03f548` are R1 (neither), R4 (no password) and R5 (empty passwords), and two docstrings that link with mkdocstrings cross-references instead of Sphinx roles, which this repository's docs render as plain text (README, "Writing docstrings").
- **F2** `RoleAssignmentConfig` lives in `commons.settings`, which `commons.users` imports; its validator imports `_normalize_path` inside the function, as a module-level import would be circular.
- **F3** `upsert_role()` failed on `main` already for a role that mixes stored and new permissions (`UNIQUE constraint failed: permissions.name`): adding the new permission cascaded to the role, and the merge inserted its stored permissions again. It now builds the role in the session like the default role sync, without merging the given objects.
- **F4** Default roles are synced in `SQLUsersRepository.__init__`, before an app calls `init_from_settings()`, so users in the settings can be assigned default roles.

Rollout: PR #25 into `main`; release-please releases it as 1.2.0, which apps on `versions/1` get with their next dependency update. Local databases created before must be deleted (no migration); UAT keeps no data (no app deploys with the Azure SQL database).

Open after this change:

- app--casesight: create email-only users without a password instead of the hash of a random secret, and introduce its roles (global admin on `/app`, tenant admin on `/app/tenants/<id>`) with the delegation rule in its domain. Owner: Michael Wellner.
- app--beleglotse and app--cross-border-rules: enabling their commented-out permission checks, which now work as written. Owner: the developer of each app.
