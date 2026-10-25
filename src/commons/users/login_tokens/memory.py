"""
In-memory storage of login requests, for a single process.
"""

import threading
from dataclasses import replace
from datetime import datetime

from commons.users.login_tokens.model import LoginTokenRequest
from commons.users.login_tokens.store import LoginTokenStore


class InMemoryLoginTokenStore(LoginTokenStore):
    """
    Keeps login requests in a dict, guarded by a lock.

    Suited for development, tests and apps running a single process. With
    several processes or workers, each would have its own requests (a link
    sent by one worker wouldn't work on another) and its own rate limits;
    use ``SQLLoginTokenStore`` there.
    """

    def __init__(self) -> None:
        self._requests: dict[str, LoginTokenRequest] = {}
        self._lock = threading.Lock()

    def add(self, request: LoginTokenRequest) -> None:
        with self._lock:
            self._requests[request.id] = replace(request)

    def get(self, request_id: str) -> LoginTokenRequest | None:
        with self._lock:
            request = self._requests.get(request_id)
            return replace(request) if request else None

    def find_by_link_hash(self, link_hash: str) -> LoginTokenRequest | None:
        with self._lock:
            for request in self._requests.values():
                if request.link_hash == link_hash:
                    return replace(request)
            return None

    def consume(self, request_id: str, now: datetime) -> bool:
        with self._lock:
            request = self._requests.get(request_id)
            if request is None or request.consumed_at is not None or request.expires_at <= now:
                return False
            request.consumed_at = now
            return True

    def record_failed_attempt(self, request_id: str) -> int:
        with self._lock:
            request = self._requests.get(request_id)
            if request is None:
                return 0
            request.failed_attempts += 1
            return request.failed_attempts

    def count_requests(
        self,
        *,
        email_hash: str,
        since: datetime,
    ) -> int:
        with self._lock:
            return sum(
                1
                for request in self._requests.values()
                if request.email_hash == email_hash and request.created_at >= since
            )

    def delete_expired(self, before: datetime) -> int:
        with self._lock:
            expired = [request_id for request_id, r in self._requests.items() if r.expires_at < before]
            for request_id in expired:
                del self._requests[request_id]
            return len(expired)
