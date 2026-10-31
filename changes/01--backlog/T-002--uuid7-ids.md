# T-002 Time-ordered UUIDv7 ids

## Problem

`commons` generates its ids with `uuid4` (`EntityMixin`, users, roles, login requests, jobs), so they are random: primary keys index poorly and ids say nothing about the order objects were created in. With Python 3.14 (T-001), `uuid.uuid7` is in the standard library, and the events of T-001 already use it.

## Proposed outcome

- New ids of `commons` are UUIDv7 strings, generated in one place; existing ids stay valid (same 36-character form, `ID_LENGTH`).
