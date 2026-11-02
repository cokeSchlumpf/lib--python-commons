# T-009 User access period

## Problem

Apps maintain their users in the app now (T-008 of `app--casesight`: an admin section to create, edit and delete users), but `commons` can't express that a user may not work right now. A user either exists and can sign in, or is deleted. An admin can't switch a user off for a while without losing them and their role assignments, and can't give someone access for a limited time, e.g. a demo access for two weeks. An app that wanted this would have to check it in its own code, while sign-in (`authenticate`, `LoginTokenService`) and permission checks (`has_permission`) happen in `commons` and pyhx, so a switched-off user could still sign in. `UsersRepository` also has no way to list users, so an admin page can't show them.

## Proposed outcome

- A registered user has an active flag (default active) and an optional access period (from, until; each optional), stored as UTC date-times.
- A user who is inactive or outside their period can't sign in: no password login, no login link or code is sent (the result looks the same as for an unknown address), and a link or code requested before can't be redeemed.
- Such a user has no permissions (`has_permission` is false), so an app built on pyhx, which loads the user from the database on every request, refuses them access from the next request on, even within a running session.
- One method answers whether a user can sign in at a given time, so apps can show it.
- `UsersRepository` can list all registered users.
- Not part of this change: signing a user out of a running session (pyhx), time zones (the app converts what an admin enters), migrating existing tables.

## Affected users and systems

- **Apps using `SQLUsersRepository`:** `registered_users` gets three columns; as with 1.2 and 1.4, existing tables are not migrated, so a database created before this version is recreated.
- **`app--casesight` (T-008):** uses the flag, the period and the listing in its admin section; its spec is the source of this change: [spec](https://github.com/cokeSchlumpf/app--casesight/blob/feature/pages-and-roles/changes/02--open/T-008--pages-and-roles/spec.md).
- **pyhx:** no change; its login pages and its session use the repository and the login token service, which refuse such users.
- **`app--beleglotse`, `app--cross-border-rules`:** recreate their database when they update to this version; their users are synced from settings.

## Constraints

- Backwards compatible within `versions/1` (a `feat`, minor release): existing calls, settings and stored users keep working; a user without the new values is active without limit.
- No schema migrations (decision D1 of T-007).
- Works on SQLite and Azure SQL.

## Open questions

None.
