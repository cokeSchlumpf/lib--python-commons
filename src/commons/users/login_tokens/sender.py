"""
Delivery of login links and codes to the user.

The service decides *when* to send and *what* (link, code, expiry); a
sender decides *how* (log, email, …). Apps plug in their own sender via
``SendLoginTokenPort``.
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from commons.users.user import RegisteredUser

LOG = logging.getLogger(__name__)


@dataclass(frozen=True)
class LoginTokenMessage:
    """
    What to deliver to the user.

    Attributes:
        user: The user who requested the login.
        email: The address the user entered (and the message goes to).
        link: Absolute URL that logs the user in when opened.
        code: Code the user can type in instead, in the browser that
            requested the login.
        expires_at: When the link and the code stop working (UTC).
        locale: The language to write the message in (e.g. ``"de"``), as the
            caller resolved it for the user; ``None`` lets the sender choose.
    """

    user: RegisteredUser
    email: str
    link: str
    code: str
    expires_at: datetime
    locale: str | None = None


class SendLoginTokenPort(Protocol):
    """
    Delivers a login link and code to a user.

    Implementations must not swallow errors: if the message can't be
    delivered, raise, so the caller can tell the user to try again.

    Example::

        class TeamsLoginTokenSender:
            def send_login_token(self, message: LoginTokenMessage) -> None:
                post_to_teams(message.user, f"Your code: {message.code}")
    """

    def send_login_token(self, message: LoginTokenMessage) -> None:
        """
        Deliver the message to the user.

        Args:
            message: The link, code and expiry to deliver.
        """
        ...


class LoggingLoginTokenSender:
    """
    Writes login links and codes to the log instead of sending them.

    The default sender: lets an app use login tokens in development without
    a mail server. Never use it in production — anyone with access to the
    logs could log in as any user.

    Args:
        logger: The logger to write to; defaults to this module's logger.
        level: The log level; defaults to WARNING, so the line shows up with
            default logging configuration.
    """

    def __init__(self, logger: logging.Logger | None = None, level: int = logging.WARNING) -> None:
        self._logger = logger or LOG
        self._level = level

    def send_login_token(self, message: LoginTokenMessage) -> None:
        self._logger.log(
            self._level,
            "Login token for %s (%s): code %s, link %s (valid until %s)",
            message.user.username,
            message.email,
            message.code,
            message.link,
            message.expires_at.isoformat(timespec="seconds"),
        )
