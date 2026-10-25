"""
Data types of the login-token flow.

A ``LoginTokenRequest`` is one "send me a login link" request. It holds only
hashes of the secrets (the link token and the code), never the secrets
themselves, so a leaked store can't be used to log in.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from commons.users.user import RegisteredUser


@dataclass
class LoginTokenRequest:
    """
    One login request of a registered user, as kept by a ``LoginTokenStore``.

    Requests for unknown email addresses are not stored: nothing is kept
    about people who aren't users.

    Attributes:
        id: Random identifier of the request. Callers keep it (e.g. in the
            session) to redeem the code in the same browser.
        email_hash: HMAC-SHA256 of the lower-cased email address, for the
            per-address rate limit.
        created_at: When the request was made (timezone-aware, UTC).
        expires_at: When the link and the code stop working (UTC).
        user_id: The user to log in.
        link_hash: HMAC-SHA256 of the link token.
        code_hash: HMAC-SHA256 of ``"{id}:{code}"``.
        redirect_to: Where the caller wants to go after logging in.
        failed_attempts: Number of wrong codes entered so far.
        consumed_at: When the request was redeemed (or invalidated); ``None``
            while it's still usable.
    """

    id: str
    user_id: str
    email_hash: str
    link_hash: str
    code_hash: str
    created_at: datetime
    expires_at: datetime
    redirect_to: str | None = None
    failed_attempts: int = 0
    consumed_at: datetime | None = None


class RequestStatus(StrEnum):
    """
    Outcome of ``LoginTokenService.request_login``.

    Callers should show the same message for every status ("If an account
    exists, we've sent you a link"), so the response doesn't reveal which
    addresses are registered or rate limited.
    """

    SENT = "sent"
    """A link and a code were sent to the user."""

    UNKNOWN_EMAIL = "unknown_email"
    """No user has this address; nothing was sent or stored."""

    RATE_LIMITED = "rate_limited"
    """Too many requests for this address; nothing was sent."""


@dataclass(frozen=True)
class LoginRequest:
    """
    Result of ``LoginTokenService.request_login``.

    Attributes:
        request_id: Identifier to redeem the code with (keep it, e.g. in the
            session). Present for every status, so callers can treat all
            outcomes alike; for an unknown address or a rate-limited request
            it's random and stored nowhere, so a code for it fails.
        status: What happened; don't show it to the user (see ``RequestStatus``).
        expires_at: When the link and the code expire.
    """

    request_id: str
    status: RequestStatus
    expires_at: datetime


class RedeemStatus(StrEnum):
    """Outcome of redeeming a link or a code."""

    OK = "ok"
    """The user is logged in."""

    INVALID = "invalid"
    """Unknown link or request, or a wrong code."""

    EXPIRED = "expired"
    """The link or code is too old."""

    USED = "used"
    """The request was already redeemed (or invalidated)."""

    TOO_MANY_ATTEMPTS = "too_many_attempts"
    """Too many wrong codes; the request is invalidated."""


@dataclass(frozen=True)
class RedeemResult:
    """
    Result of ``LoginTokenService.redeem_link`` / ``redeem_code``.

    Attributes:
        status: Whether the redemption succeeded and, if not, why.
        user: The user to log in; only set when ``status`` is ``OK``.
        redirect_to: The ``redirect_to`` given when the login was requested;
            only set when ``status`` is ``OK``.
    """

    status: RedeemStatus
    user: RegisteredUser | None = None
    redirect_to: str | None = None

    @property
    def ok(self) -> bool:
        """``True`` if the user may be logged in."""
        return self.status is RedeemStatus.OK
