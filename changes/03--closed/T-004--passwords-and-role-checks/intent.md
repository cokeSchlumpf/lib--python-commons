# T-004 Hashed passwords and safe role checks

## Problem

`commons.users` is the user management of our apps: who a user is, how they prove it, and what they may do where. Two parts of it can't be relied on yet.

**Passwords in the settings.** Users that apps bootstrap from the settings (`[[app.users]]`, read as `commons.settings.StandardUser`) can only be given a plain-text `password`. `UsersRepository.init_from_settings()` hashes it with bcrypt before storing it, but the plain text has to sit in the settings: in `settings.secrets.toml`, in `APP__*` app settings in Azure, or in the Key Vault. Anyone who can read the settings can sign in as that user, and there is no tool to produce a hash that could be stored instead. In addition, `init_from_settings()` upserts every configured user on each start: a password a user changed in the app (`update_password()`) is reset to the configured one with the next restart or deployment, and the configured roles are assigned again each time.

`kpmg--lib--commons`, a close sibling of this library, already solved this in commit `f03f548` ("feat: Allow hashed user passwords"); this library should get the same behaviour.

**Users without a password.** commons has no way to say "this user has no password". Apps with email sign-in only (app--casesight) store the bcrypt hash of a random secret they throw away. That works, but only by convention: nothing stops `hash_password("")` from creating a user who signs in with an empty password (pyhx's login form accepts an empty one), and nothing tells a reader that the user is meant to have no password.

**Scoped role checks.** `commons.users` has the right model for scoped roles: roles are sets of permission paths, a `RoleAssignment` grants a role to a registered user on a scope path, and `has_permission` lets a role on `/app` apply to `/app/tenants/<id>`. Apps like app--casesight want to rely on it for tenant isolation (global admin on `/app`, tenant admin on `/app/tenants/<id>`), but today it can't be trusted for that:

- Path checks can be bypassed: `has_permission(tenant_a_admin, "/app/tenants/<a>/../<b>", "/write")` is `True`, because `PurePosixPath` doesn't resolve `..`. The name validators of `Scope` and `Permission` never run, because SQLModel table models skip validation, so `Scope(name="/App/Has Spaces")` is accepted.
- The same (user, scope, role) can be assigned any number of times; nothing makes assignments unique.
- An assignment to a role that doesn't exist is accepted (on SQLite without foreign keys), and from then on `has_permission` raises `KeyError` for that user on every scope, because the role is resolved before the scope is compared.
- Roles defined in code (`default_roles`) live only in memory: they aren't in the `roles` table, so with foreign keys enforced (Postgres, or SQLite with `PRAGMA foreign_keys=ON`) they can't be assigned at all (`IntegrityError`), and `list_roles()` doesn't show them.
- You can only ask which roles one user has, not who has which role in a scope (e.g. the admins of a tenant), and deleting a tenant leaves its assignments behind.
- There are no tests for roles, scope inheritance or permission checks, so none of this was noticed.

Today nobody notices, because no app checks permissions yet. The first app that does would get a tenant isolation hole or crashing permission checks.

## Proposed outcome

Passwords:

- A user in the settings has `password` (plain text, hashed on creation, as today), `password_hash` (a bcrypt hash, stored as is), or neither; a user with both is rejected when the settings are read.
- A user without a password can never sign in with one: `authenticate()` returns `None` for them, whatever password is entered. Apps with email sign-in only no longer need the hash of a random, discarded secret.
- An empty password is never a valid password: `hash_password()` and `update_password()` reject it.
- `python -m commons.users hash-password` prints a bcrypt hash for a password: it prompts twice without echo, or reads it from stdin with `--stdin` (for scripts). The printed value goes into `password_hash`.
- `init_from_settings()` creates only users that don't exist yet, with their configured roles; existing users are left as they are in the database (password, names, roles), so passwords changed in the app survive restarts.
- This part follows `kpmg--lib--commons` `f03f548` 1:1 (code, docstrings, tests), so both libraries stay alike, except for users without a password, which `f03f548` rejects.

Role checks:

- Scope and permission paths are normalized and validated wherever they enter: when assigning, when defining roles, and when checking. A path with `..`, `.`, empty segments or invalid characters is rejected, not silently matched.
- Assignments are unique per (user, scope, role); assigning the same role twice is idempotent.
- Assigning an unknown role is rejected.
- `has_permission` doesn't raise because of one unresolvable assignment; it skips it (fail closed) and the other assignments still count.
- Default roles are synced into the `roles` table when the repository is created, marked as default roles (`is_default_role`); the code is their source of truth, so their permissions in the database follow the code. Roles the app creates at runtime (`upsert_role()`) are not marked and never touched by the sync.
- A default role that was removed from the code is deleted from the database together with its assignments on the next start, even if that revokes access silently.
- Assignments can be listed by scope (who has which role in a scope, e.g. the admins of a tenant) and removed by scope (e.g. when a tenant is deleted).
- Tests cover role definition, the default role sync, assignment, listing and removing by scope, scope inheritance, permission inheritance, the rejected paths, and the edge cases above, on SQLite with foreign keys on and off.

Not part of this change: deciding who may assign which role (delegation) — that is the app's job, not the library's; encrypting other settings, a Key Vault integration (T-003); switching the apps' own configured users to `password_hash` or any other follow-up in the apps; other user types, the login token flow, and making the API async or transactional.

## Affected users and systems

- **`lib--python-commons`:** `commons.settings.StandardUser` and `StandardUserSettings`; `commons.users` (new `__main__.py`, `user.py`, `repository.py`, `sql.py`, `__init__.py`); new tests for settings users and for roles and permissions.
- **Apps on `versions/1` that call `init_from_settings()`** (`app--hello`, `app--beleglotse`, `app--cross-border-rules`): their configured users keep working unchanged; changing a configured user's password, names or roles in the settings no longer updates an existing user (it takes `update_password()` or a reset of the app's data). They can move to `password_hash` whenever they like.
- **All apps on `versions/1`, including app--casesight and pyhx's auth addon:** may notice minor behaviour changes in role checks, e.g. paths that were accepted before are rejected; none of them checks permissions yet.
- **Existing databases:** the `roles` table gets a new column and `role_assignments` a uniqueness rule; databases created before this change must be recreated (delete the app's data). No real app has data that matters yet.
- **Apps on `versions/0`:** unaffected.

## Constraints

- A minor release (`feat`, 1.2.0) on `versions/1`. The changed behaviour (`init_from_settings()` no longer updates existing users; stricter role checks; recreated databases) is called out in the changelog and the pull request, not marked as breaking (`!`), since no app depends on it yet.
- Compatible for the settings: existing `password` entries stay valid; nothing to change in the apps' settings to upgrade.
- The hash must match the repository's password verifier (bcrypt by default); the CLI uses the default hasher.
- Plain-text passwords are never printed or logged by the CLI.
- No new dependency (`argparse`, `getpass` and `bcrypt` are already available).
- No database migration: `commons` has no migration framework, and no real app has data yet.
- Security: invalid input at this trust boundary is rejected, never silently corrected into a different scope or a usable empty password.

## Open questions

None.
