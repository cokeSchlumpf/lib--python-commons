"""
Passwordless login with a link or code sent to a registered user.

Overview
--------

- **LoginTokenService**: The flow. ``request_login(email, ...)`` creates a
  request with a random link token and a numeric code and hands both to a
  sender; ``redeem_link(token)`` / ``redeem_code(request_id, code)`` return
  the user to log in. Single use, short-lived, rate limited.
- **LoginTokenStore**: Where requests are kept (hashes only, never the
  secrets). ``InMemoryLoginTokenStore`` for a single process,
  ``SQLLoginTokenStore`` for several processes or workers.
- **SendLoginTokenPort**: How link and code reach the user. The default
  ``LoggingLoginTokenSender`` writes them to the log (development only);
  ``SMTPLoginTokenSender`` sends them by email via the SMTP server of
  ``app.smtp`` (see :mod:`commons.users.login_tokens.smtp`).
- **LoginTokenSettings**: Validity, code length and the rate limit, read from
  ``app.login_tokens.*``.

The module is synchronous like :mod:`commons.users`; async apps call it via
``asyncio.to_thread``. Users are looked up with
``UsersRepository.find_user_by_email``.

Example::

    from commons.users.login_tokens import InMemoryLoginTokenStore, LoginTokenService

    service = LoginTokenService(users, InMemoryLoginTokenStore(), secret_key=app_secret)

    request = service.request_login(
        "jane@example.com",
        link_for=lambda token: f"https://app.example.com/login/token?t={token}",
    )
    # Show the same message whatever request.status is.

    result = service.redeem_code(request.request_id, "123456")
    if result.ok:
        ...  # log result.user in
"""

from .memory import InMemoryLoginTokenStore
from .model import (
    LoginRequest,
    LoginTokenRequest,
    RedeemResult,
    RedeemStatus,
    RequestStatus,
)
from .sender import LoggingLoginTokenSender, LoginTokenMessage, SendLoginTokenPort
from .service import LoginTokenService, LoginTokenSettings
from .smtp import ComposeLoginTokenMail, LoginTokenMail, SMTPLoginTokenSender
from .sql import SQLLoginTokenStore
from .store import LoginTokenStore

__all__ = [
    "ComposeLoginTokenMail",
    "InMemoryLoginTokenStore",
    "LoggingLoginTokenSender",
    "LoginRequest",
    "LoginTokenMail",
    "LoginTokenMessage",
    "LoginTokenRequest",
    "LoginTokenService",
    "LoginTokenSettings",
    "LoginTokenStore",
    "RedeemResult",
    "RedeemStatus",
    "RequestStatus",
    "SMTPLoginTokenSender",
    "SQLLoginTokenStore",
    "SendLoginTokenPort",
]
