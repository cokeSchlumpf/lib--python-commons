# T-009 User access period: spec

## Requirements

### Access of a user

- **R1** `RegisteredUser` has `is_active: bool` (default `True`), `valid_from: datetime | None` and `valid_until: datetime | None` (default `None`, timezone-aware, stored as UTC; `valid_until` is exclusive). `RegisteredUser.create()` takes them as optional keyword arguments; the fields can be changed and saved with `upsert_user`.
- **R2** `RegisteredUser.can_sign_in(at: datetime | None = None) -> bool` is true if the user is active and `at` (default: now, UTC) is not before `valid_from` and before `valid_until`; a missing bound doesn't limit.
- **R3** A user for whom `can_sign_in()` is false has no permission: `has_permission` and `registered_user_has_permission` return `False`, `check_permission` raises, also for permissions granted through `registered_default_permissions`.

### Signing in

- **R4** `authenticate()` returns `None` for such a user, even with the right password.
- **R5** `LoginTokenService.request_login()` sends nothing and stores no request for such a user, and returns a new status `RequestStatus.USER_INACTIVE` with a random request id, like for an unknown address.
- **R6** Redeeming a link or code of a request whose user can't sign in at the time of redeeming fails with a new status `RedeemStatus.USER_INACTIVE` (no user); the request is consumed.

### Listing users

- **R7** `UsersRepository.list_users() -> list[RegisteredUser]` returns all registered users, ordered by username.

### Compatibility and documentation

- **R8** Existing calls keep working; users created without the new values are active without limit. Existing `registered_users` tables are not migrated: the `SQLUsersRepository` docstring names 1.6 among the versions whose databases must be recreated.
- **R9** The docstrings (API reference) describe the access period, its effect on sign-in and permissions, and `list_users`.
- **R10** Tests cover R1 to R7 on SQLite: the bounds of the period (before, at `valid_from`, before and at `valid_until`), inactive users, saving and reading the fields with their time zone, permissions through assignments and default permissions, password login, requesting and redeeming links and codes, listing.

## Design

`user.py`, `RegisteredUser`: three columns next to `locale_`, in the style of the existing fields (`is_active_` with `Column("is_active", Boolean, nullable=False, default=True)`, `valid_from_`/`valid_until_` with `UTCDateTime` of `commons.database.types`, which keeps values UTC-aware on SQLite and Azure SQL; see D1 of the plan), properties with setters, and `can_sign_in`:

```python
def can_sign_in(self, at: datetime | None = None) -> bool:
    at = at or utc_now()
    return (
        self.is_active
        and (self.valid_from is None or self.valid_from <= at)
        and (self.valid_until is None or at < self.valid_until)
    )
```

`repository.py`: `authenticate` checks `user.can_sign_in()` after finding the user; `registered_user_has_permission` returns `False` first if `not user.can_sign_in()` (`has_permission` and `check_permission` go through it). `list_users` is abstract in `UsersRepository` and implemented in `SQLUsersRepository` with `select(RegisteredUser).order_by(RegisteredUser.username_)`.

`login_tokens`: `RequestStatus.USER_INACTIVE` and `RedeemStatus.USER_INACTIVE` (additive). `request_login` returns it right after finding the user, before the rate limit, with `user.can_sign_in(now)` and the service's clock; `_redeem` checks it after loading the user, also with the clock.

pyhx needs no change: its email login treats every request status alike and every non-OK redeem result as failure, and its session loads the user on every request, so R3 takes effect immediately.

## Alternatives considered

- **Filtering inactive users in `find_user_by_*`:** would hide them from admin pages and from `init_from_settings`, which would then create them again.
- **Dates instead of date-times:** the app would lose the time zone it converts with; a date-time is exact and the app decides what a day means.
- **Migrating `registered_users`:** rejected by the developer for T-007 (D1); the same rule applies.

## Constraint mapping

| Constraint (intent) | Met by |
| --- | --- |
| Backwards compatible within `versions/1` | R1 (defaults), R5/R6 (new enum values only), R8 |
| No schema migrations | R8 |
| SQLite and Azure SQL | R1 (`UTCDateTime`, `Boolean`), R10 |

## Open questions

None.

## Areas of concern

1. **Databases before 1.6 break** (R8): selecting users fails on an old table (missing columns). Named in the docstring and the release notes; CaseSight has only local SQLite, beleglotse and cross-border-rules recreate their databases on their next update. Owner: Michael Wellner.
2. **Permission checks per request** (R3): `can_sign_in` is a check on the loaded user, no extra query. Owner: agent.

## Out of scope

- Signing a user out of a running session (pyhx); time zones; a UI.

## Outcome

Implemented as specified, with these deviations and findings (from the plan, removed at close-out):

- **D1** `valid_from` and `valid_until` are plain `DateTime` columns holding naive UTC instead of `UTCDateTime`: `commons.database` imports `commons.users`, so `commons.users.user` can't import it. The properties return aware UTC values, so R1 holds.
- **F1** `check_permission` raises `LookupError` (not `PermissionError`); unchanged.
- **F2** pyhx needs no change: it checks only `result.ok` after redeeming and shows the same page for every request status.

Rollout: PR cokeSchlumpf/lib--python-commons#41, released with the next Release PR (1.6.0); databases created before 1.6 are recreated.

Open after this change: `app--casesight` T-008 uses the access period and `list_users` (Michael Wellner); `app--beleglotse` and `app--cross-border-rules` recreate their databases on their next update of `commons`.
