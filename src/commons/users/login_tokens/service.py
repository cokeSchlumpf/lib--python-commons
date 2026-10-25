"""
The login-token flow: request a link and code, redeem one of them.
"""

import hashlib
import hmac
import secrets
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from commons.users.login_tokens.model import (
    LoginRequest,
    LoginTokenRequest,
    RedeemResult,
    RedeemStatus,
    RequestStatus,
)
from commons.users.login_tokens.sender import LoggingLoginTokenSender, LoginTokenMessage, SendLoginTokenPort
from commons.users.login_tokens.store import LoginTokenStore
from commons.settings import read_settings_object
from commons.users.repository import UsersRepository


class LoginTokenSettings:
    """
    Settings of the login-token flow.

    Read from ``app.login_tokens.*`` (see :mod:`commons.settings`); every
    field has a default, so no configuration is needed.

    TOML::

        [app.login_tokens]
        token_ttl = 900  # link and code validity, seconds
        code_length = 6  # digits of the code
        max_code_attempts = 5  # wrong codes before the request is invalidated
        max_requests_per_email = 3  # requests per address ...
        email_window = 900  # ... within this many seconds

    Env var overrides follow the standard pattern, e.g.
    ``APP__LOGIN_TOKENS__TOKEN_TTL``.
    """

    def __init__(
        self,
        token_ttl: int = 15 * 60,
        code_length: int = 6,
        max_code_attempts: int = 5,
        max_requests_per_email: int = 3,
        email_window: int = 15 * 60,
        **_kwargs: Any,
    ) -> None:
        self.token_ttl = int(token_ttl)
        self.code_length = int(code_length)
        self.max_code_attempts = int(max_code_attempts)
        self.max_requests_per_email = int(max_requests_per_email)
        self.email_window = int(email_window)

    @staticmethod
    def read() -> "LoginTokenSettings":
        """Read the settings; defaults if ``app.login_tokens`` is not configured."""
        try:
            return read_settings_object("login_tokens", LoginTokenSettings)
        except KeyError:
            return LoginTokenSettings()


def _normalize_email(email: str) -> str:
    return email.strip().lower()


class LoginTokenService:
    """
    Lets registered users log in with a link or code sent to their email
    address.

    ``request_login`` creates a request with a random link token and a
    numeric code, stores only their hashes, and hands both to the sender.
    The user then either opens the link (``redeem_link``) or types the code
    into the browser that requested it (``redeem_code``). Redeeming one
    invalidates the other; both expire after ``token_ttl``.

    The rate limit counts the stored requests per address (against flooding
    one person's inbox). No client data such as IP addresses is stored.
    Wrong codes count per request; after ``max_code_attempts`` the request
    is invalidated, which makes guessing a 6-digit code hopeless.

    All methods are synchronous; call them via ``asyncio.to_thread`` from
    async code.

    Everything stored is an HMAC-SHA256 keyed with ``secret_key``: without
    the key, neither an address can be confirmed from ``email_hash`` (as a
    plain hash of known addresses would allow) nor a 6-digit code be
    brute-forced from ``code_hash``.

    Args:
        users: Repository to look users up by email and id.
        store: Where requests are kept.
        secret_key: Key for hashing what is stored (e.g. the app's session
            secret); at least 16 characters, and the same for every process
            sharing the store.
        sender: Delivers link and code; defaults to ``LoggingLoginTokenSender``
            (development only).
        settings: Defaults to ``LoginTokenSettings.read()``.
        clock: Returns the current time (UTC); for tests.

    Example::

        service = LoginTokenService(users, InMemoryLoginTokenStore(), secret_key=app_secret)

        request = service.request_login(
            "jane@example.com",
            link_for=lambda token: f"https://app.example.com/login/token?t={token}",
        )
        # keep request.request_id, e.g. in the session

        result = service.redeem_code(request.request_id, "123456")
        if result.ok:
            log_in(result.user)
    """

    def __init__(
        self,
        users: UsersRepository,
        store: LoginTokenStore,
        *,
        secret_key: str,
        sender: SendLoginTokenPort | None = None,
        settings: LoginTokenSettings | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if len(secret_key) < 16:
            raise ValueError("`secret_key` must be at least 16 characters long.")

        self._key = secret_key.encode("utf-8")
        self._users = users
        self._store = store
        self._sender = sender or LoggingLoginTokenSender()
        self._settings = settings or LoginTokenSettings.read()
        self._clock = clock or (lambda: datetime.now(UTC))

    @property
    def settings(self) -> LoginTokenSettings:
        return self._settings

    def request_login(
        self,
        email: str,
        *,
        link_for: Callable[[str], str],
        redirect_to: str | None = None,
    ) -> LoginRequest:
        """
        Request a login link and code for an email address.

        Returns a ``request_id`` for every outcome, and callers should show
        the same message for every status, so the response doesn't reveal
        whether the address is registered.

        Args:
            email: The address the user entered.
            link_for: Builds the absolute login URL from the link token.
            redirect_to: Where to go after logging in; returned by the
                redeem methods.

        Returns:
            The request id, what happened, and when the link expires.

        Raises:
            Exception: Whatever the sender raises if delivery fails.
        """
        now = self._clock()
        expires_at = now + timedelta(seconds=self._settings.token_ttl)
        normalized = _normalize_email(email)
        email_hash = self._hash(normalized)

        # Unknown addresses and rate-limited requests are not stored; their
        # random request id exists nowhere, so a code entered for it fails.
        user = self._users.find_user_by_email(normalized)
        if user is None:
            return LoginRequest(uuid4().hex, RequestStatus.UNKNOWN_EMAIL, expires_at)

        if self._is_rate_limited(now, email_hash):
            return LoginRequest(uuid4().hex, RequestStatus.RATE_LIMITED, expires_at)

        request_id = uuid4().hex
        link_token = secrets.token_urlsafe(32)
        code = str(secrets.randbelow(10**self._settings.code_length)).zfill(self._settings.code_length)

        request = LoginTokenRequest(
            id=request_id,
            user_id=user.id,
            email_hash=email_hash,
            link_hash=self._hash(link_token),
            code_hash=self._hash(f"{request_id}:{code}"),
            created_at=now,
            expires_at=expires_at,
            redirect_to=redirect_to,
        )
        self._store.add(request)

        self._sender.send_login_token(
            LoginTokenMessage(
                user=user,
                email=email.strip(),
                link=link_for(link_token),
                code=code,
                expires_at=expires_at,
            )
        )
        return LoginRequest(request.id, RequestStatus.SENT, expires_at)

    def redeem_link(self, link_token: str) -> RedeemResult:
        """
        Redeem the token from a login link.

        Args:
            link_token: The token from the link.

        Returns:
            ``OK`` with the user, or why the link doesn't work.
        """
        request = self._store.find_by_link_hash(self._hash(link_token))
        if request is None:
            return RedeemResult(RedeemStatus.INVALID)
        return self._redeem(request)

    def redeem_code(self, request_id: str, code: str) -> RedeemResult:
        """
        Redeem a code typed in by the user.

        Args:
            request_id: The id returned by ``request_login``.
            code: The code the user entered.

        Returns:
            ``OK`` with the user, or why the code doesn't work.
        """
        request = self._store.get(request_id)
        if request is None:
            return RedeemResult(RedeemStatus.INVALID)
        if request.consumed_at is not None:
            return RedeemResult(self._consumed_status(request))
        if request.expires_at <= self._clock():
            return RedeemResult(RedeemStatus.EXPIRED)

        entered = self._hash(f"{request.id}:{code.strip()}")
        if not hmac.compare_digest(request.code_hash, entered):
            attempts = self._store.record_failed_attempt(request.id)
            if attempts >= self._settings.max_code_attempts:
                self._store.consume(request.id, self._clock())
                return RedeemResult(RedeemStatus.TOO_MANY_ATTEMPTS)
            return RedeemResult(RedeemStatus.INVALID)

        return self._redeem(request)

    def purge_expired(self) -> int:
        """
        Delete requests no longer needed, neither to log in nor for the
        rate limit.

        Returns:
            The number of deleted requests.
        """
        keep = max(self._settings.token_ttl, self._settings.email_window)
        return self._store.delete_expired(self._clock() - timedelta(seconds=keep))

    def _hash(self, value: str) -> str:
        return hmac.new(self._key, value.encode("utf-8"), hashlib.sha256).hexdigest()

    def _redeem(self, request: LoginTokenRequest) -> RedeemResult:
        now = self._clock()
        if request.consumed_at is not None:
            return RedeemResult(self._consumed_status(request))
        if request.expires_at <= now:
            return RedeemResult(RedeemStatus.EXPIRED)
        if not self._store.consume(request.id, now):
            return RedeemResult(RedeemStatus.USED)

        user = self._users.find_user_by_id(request.user_id)
        if user is None:
            return RedeemResult(RedeemStatus.INVALID)
        return RedeemResult(RedeemStatus.OK, user=user, redirect_to=request.redirect_to)

    def _consumed_status(self, request: LoginTokenRequest) -> RedeemStatus:
        if request.failed_attempts >= self._settings.max_code_attempts:
            return RedeemStatus.TOO_MANY_ATTEMPTS
        return RedeemStatus.USED

    def _is_rate_limited(self, now: datetime, email_hash: str) -> bool:
        since = now - timedelta(seconds=self._settings.email_window)
        count = self._store.count_requests(email_hash=email_hash, since=since)
        return count >= self._settings.max_requests_per_email
