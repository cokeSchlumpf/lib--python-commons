"""Ids for new objects."""

from uuid import uuid7


def new_id() -> str:
    """Return a new id: a time-ordered UUIDv7 as a 36-character string.

    Ids created one after another in a process compare in creation order, so as primary keys they are appended to
    the index instead of landing anywhere in it. They reveal when they were created; don't use them as secrets.

    Returns:
        The id, e.g. ``"019a3b2c-7d4e-7f10-8a2b-3c4d5e6f7a8b"``.
    """
    return str(uuid7())
