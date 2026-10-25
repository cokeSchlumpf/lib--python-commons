"""
Abstract storage of login requests.
"""

import abc
from datetime import datetime

from commons.users.login_tokens.model import LoginTokenRequest


class LoginTokenStore(abc.ABC):
    """
    Abstract base class for storing login requests.

    Implementations must be safe to call from several threads (callers in
    async web apps run them via ``asyncio.to_thread``). ``consume`` must be
    atomic: of two concurrent calls for the same request, only one may
    succeed, so a link or code can't be redeemed twice.

    The rate limit of ``LoginTokenService`` is a count over the stored
    requests (``count_requests``), so a store shared by several processes
    (e.g. ``SQLLoginTokenStore``) also shares the limits.

    See Also:
        InMemoryLoginTokenStore: For a single process (default, tests).
        SQLLoginTokenStore: For several processes or workers.
    """

    @abc.abstractmethod
    def add(self, request: LoginTokenRequest) -> None:
        """
        Store a new request.

        Args:
            request: The request to store.
        """

    @abc.abstractmethod
    def get(self, request_id: str) -> LoginTokenRequest | None:
        """
        Find a request by its id.

        Args:
            request_id: The request's id.

        Returns:
            The request, or None if there is none with this id.
        """

    @abc.abstractmethod
    def find_by_link_hash(self, link_hash: str) -> LoginTokenRequest | None:
        """
        Find a request by the hash of its link token.

        Args:
            link_hash: HMAC-SHA256 of the link token (see ``LoginTokenService``).

        Returns:
            The request, or None if no request has this link.
        """

    @abc.abstractmethod
    def consume(self, request_id: str, now: datetime) -> bool:
        """
        Mark a request as redeemed, if it's still usable.

        Atomic: succeeds only if the request exists, is not consumed yet and
        has not expired at ``now``.

        Args:
            request_id: The request's id.
            now: The current time (UTC).

        Returns:
            True if this call consumed the request, False otherwise.
        """

    @abc.abstractmethod
    def record_failed_attempt(self, request_id: str) -> int:
        """
        Count one more wrong code for a request.

        Args:
            request_id: The request's id.

        Returns:
            The number of failed attempts after this one; 0 if there is no
            request with this id.
        """

    @abc.abstractmethod
    def count_requests(self, *, email_hash: str, since: datetime) -> int:
        """
        Count the requests for an address since a point in time, for rate
        limiting.

        Args:
            email_hash: Count requests for this address hash.
            since: Count requests created at or after this time (UTC).

        Returns:
            The number of matching requests.
        """

    @abc.abstractmethod
    def delete_expired(self, before: datetime) -> int:
        """
        Delete requests that expired before a point in time.

        Keep requests at least as long as the rate-limit window, or the limit
        counts too few.

        Args:
            before: Delete requests whose ``expires_at`` is before this time.

        Returns:
            The number of deleted requests.
        """
