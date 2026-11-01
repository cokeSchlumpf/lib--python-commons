import hashlib
import hmac
import threading
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine

from commons.users.login_tokens import (
    InMemoryLoginTokenStore,
    LoggingLoginTokenSender,
    LoginTokenMessage,
    LoginTokenRequest,
    LoginTokenService,
    LoginTokenSettings,
    RedeemStatus,
    RequestStatus,
    SQLLoginTokenStore,
)
from commons.users import RegisteredUser, SQLUsersRepository

START = datetime(2026, 10, 25, 9, 0, tzinfo=UTC)
SECRET = "test-secret-key-0123456789"


class Clock:
    def __init__(self) -> None:
        self.now = START

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: int) -> None:
        self.now += timedelta(seconds=seconds)


class CollectingSender:
    def __init__(self) -> None:
        self.messages: list[LoginTokenMessage] = []

    def send_login_token(self, message: LoginTokenMessage) -> None:
        self.messages.append(message)

    @property
    def last(self) -> LoginTokenMessage:
        return self.messages[-1]


@pytest.fixture
def users(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'users.db'}")
    repo = SQLUsersRepository(engine)
    repo.upsert_user(
        RegisteredUser.create(
            username="jane",
            password_hash=repo.hash_password("secret"),
            display_name="Jane Doe",
            email="Jane@Example.com",
        )
    )
    yield repo
    engine.dispose()


@pytest.fixture(params=["memory", "sql"])
def store(request, tmp_path):
    if request.param == "memory":
        yield InMemoryLoginTokenStore()
        return
    engine = create_engine(f"sqlite:///{tmp_path / 'tokens.db'}")
    yield SQLLoginTokenStore(engine)
    engine.dispose()


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def sender():
    return CollectingSender()


@pytest.fixture
def service(users, store, sender, clock):
    return LoginTokenService(
        users, store, secret_key=SECRET, sender=sender, settings=LoginTokenSettings(), clock=clock
    )


def _link(token: str) -> str:
    return f"https://app.example.com/login/token?t={token}"


def _token_from(link: str) -> str:
    return link.split("t=", 1)[1]


class TestRequestLogin:
    def test_sends_link_and_code_to_registered_user(self, service, sender):
        request = service.request_login("jane@example.com", link_for=_link)

        assert request.status is RequestStatus.SENT
        assert request.expires_at == START + timedelta(minutes=15)
        assert sender.last.user.username == "jane"
        assert sender.last.link.startswith("https://app.example.com/login/token?t=")
        assert len(sender.last.code) == 6
        assert sender.last.code.isdigit()

    def test_email_is_matched_case_insensitively_and_trimmed(self, service, sender):
        request = service.request_login("  JANE@example.COM ", link_for=_link)

        assert request.status is RequestStatus.SENT
        assert sender.last.email == "JANE@example.COM"

    def test_unknown_email_sends_and_stores_nothing_but_returns_a_request_id(self, service, sender, store):
        request = service.request_login("nobody@example.com", link_for=_link)

        assert request.status is RequestStatus.UNKNOWN_EMAIL
        assert request.request_id
        assert sender.messages == []
        assert store.get(request.request_id) is None

    def test_store_keeps_only_hashes(self, service, store, sender):
        request = service.request_login("jane@example.com", link_for=_link)
        stored = store.get(request.request_id)

        assert stored is not None
        assert _token_from(sender.last.link) not in (stored.link_hash, stored.code_hash)
        assert sender.last.code not in (stored.link_hash, stored.code_hash)
        assert "jane@example.com" != stored.email_hash


class TestSecretKey:
    def test_rejects_a_short_key(self, users, store):
        with pytest.raises(ValueError, match="at least 16"):
            LoginTokenService(users, store, secret_key="too-short")

    def test_stored_email_hash_is_keyed_not_a_plain_hash(self, service, store):
        request = service.request_login("jane@example.com", link_for=_link)
        stored = store.get(request.request_id)

        assert stored is not None
        assert stored.email_hash != hashlib.sha256(b"jane@example.com").hexdigest()
        assert stored.email_hash == hmac.new(SECRET.encode(), b"jane@example.com", hashlib.sha256).hexdigest()

    def test_service_with_another_key_cannot_redeem(self, service, users, store, sender, clock):
        request = service.request_login("jane@example.com", link_for=_link)
        other = LoginTokenService(
            users, store, secret_key="another-secret-key-987654", sender=sender, settings=LoginTokenSettings(), clock=clock
        )

        assert other.redeem_link(_token_from(sender.last.link)).status is RedeemStatus.INVALID
        assert other.redeem_code(request.request_id, sender.last.code).status is RedeemStatus.INVALID


class TestRedeemLink:
    def test_logs_user_in(self, service, sender):
        service.request_login("jane@example.com", link_for=_link, redirect_to="/dossiers")

        result = service.redeem_link(_token_from(sender.last.link))

        assert result.ok
        assert result.user is not None and result.user.username == "jane"
        assert result.redirect_to == "/dossiers"

    def test_link_works_only_once(self, service, sender):
        service.request_login("jane@example.com", link_for=_link)
        token = _token_from(sender.last.link)

        assert service.redeem_link(token).ok
        assert service.redeem_link(token).status is RedeemStatus.USED

    def test_unknown_link_is_invalid(self, service):
        assert service.redeem_link("not-a-token").status is RedeemStatus.INVALID

    def test_link_expires(self, service, sender, clock):
        service.request_login("jane@example.com", link_for=_link)
        clock.advance(15 * 60)

        assert service.redeem_link(_token_from(sender.last.link)).status is RedeemStatus.EXPIRED

    def test_redeeming_the_link_invalidates_the_code(self, service, sender):
        request = service.request_login("jane@example.com", link_for=_link)

        assert service.redeem_link(_token_from(sender.last.link)).ok
        assert service.redeem_code(request.request_id, sender.last.code).status is RedeemStatus.USED


class TestRequestIdForLink:
    def test_returns_the_request_id_without_redeeming(self, service, sender):
        request = service.request_login("jane@example.com", link_for=_link)
        token = _token_from(sender.last.link)

        assert service.request_id_for_link(token) == request.request_id
        assert service.redeem_link(token).ok

    def test_unknown_link_has_no_request(self, service):
        assert service.request_id_for_link("not-a-token") is None

    def test_redeemed_link_has_no_request(self, service, sender):
        service.request_login("jane@example.com", link_for=_link)
        token = _token_from(sender.last.link)
        service.redeem_link(token)

        assert service.request_id_for_link(token) is None

    def test_expired_link_has_no_request(self, service, sender, clock):
        service.request_login("jane@example.com", link_for=_link)
        clock.advance(15 * 60)

        assert service.request_id_for_link(_token_from(sender.last.link)) is None


class TestRedeemCode:
    def test_logs_user_in(self, service, sender):
        request = service.request_login("jane@example.com", link_for=_link, redirect_to="/x")

        result = service.redeem_code(request.request_id, sender.last.code)

        assert result.ok
        assert result.user is not None and result.user.username == "jane"
        assert result.redirect_to == "/x"

    def test_code_with_surrounding_whitespace_is_accepted(self, service, sender):
        request = service.request_login("jane@example.com", link_for=_link)

        assert service.redeem_code(request.request_id, f" {sender.last.code} ").ok

    def test_wrong_code_is_invalid(self, service, sender):
        request = service.request_login("jane@example.com", link_for=_link)
        wrong = "000000" if sender.last.code != "000000" else "111111"

        assert service.redeem_code(request.request_id, wrong).status is RedeemStatus.INVALID

    def test_too_many_wrong_codes_invalidate_the_request(self, service, sender):
        request = service.request_login("jane@example.com", link_for=_link)
        wrong = "000000" if sender.last.code != "000000" else "111111"

        statuses = [service.redeem_code(request.request_id, wrong).status for _ in range(5)]

        assert statuses == [RedeemStatus.INVALID] * 4 + [RedeemStatus.TOO_MANY_ATTEMPTS]
        # Even the right code no longer works, nor the link.
        assert service.redeem_code(request.request_id, sender.last.code).status is RedeemStatus.TOO_MANY_ATTEMPTS
        assert service.redeem_link(_token_from(sender.last.link)).status is RedeemStatus.TOO_MANY_ATTEMPTS

    def test_code_expires(self, service, sender, clock):
        request = service.request_login("jane@example.com", link_for=_link)
        clock.advance(15 * 60)

        assert service.redeem_code(request.request_id, sender.last.code).status is RedeemStatus.EXPIRED

    def test_unknown_request_id_is_invalid(self, service):
        assert service.redeem_code("nope", "123456").status is RedeemStatus.INVALID

    def test_code_for_unknown_email_fails_like_a_wrong_code(self, service):
        request = service.request_login("nobody@example.com", link_for=_link)

        assert service.redeem_code(request.request_id, "123456").status is RedeemStatus.INVALID

    def test_code_is_bound_to_its_request(self, service, sender, clock):
        first = service.request_login("jane@example.com", link_for=_link)
        code_of_first = sender.last.code
        clock.advance(1)
        second = service.request_login("jane@example.com", link_for=_link)

        if code_of_first != sender.last.code:
            assert service.redeem_code(second.request_id, code_of_first).status is RedeemStatus.INVALID
        assert service.redeem_code(first.request_id, code_of_first).ok


class TestRateLimits:
    def test_limits_requests_per_email(self, service, sender):
        statuses = [service.request_login("jane@example.com", link_for=_link).status for _ in range(4)]

        assert statuses == [RequestStatus.SENT] * 3 + [RequestStatus.RATE_LIMITED]
        assert len(sender.messages) == 3

    def test_email_limit_resets_after_its_window(self, service, clock):
        for _ in range(3):
            service.request_login("jane@example.com", link_for=_link)
        clock.advance(15 * 60 + 1)

        assert service.request_login("jane@example.com", link_for=_link).status is RequestStatus.SENT

    def test_rate_limited_request_is_not_stored_and_cannot_be_redeemed(self, service, store):
        for _ in range(3):
            service.request_login("jane@example.com", link_for=_link)
        limited = service.request_login("jane@example.com", link_for=_link)

        assert store.get(limited.request_id) is None
        assert service.redeem_code(limited.request_id, "123456").status is RedeemStatus.INVALID


class TestRequestIds:
    def test_request_ids_stay_random_uuid4_hex(self, service):
        requests = [service.request_login("jane@example.com", link_for=_link) for _ in range(4)]
        requests.append(service.request_login("nobody@example.com", link_for=_link))

        assert [r.status for r in requests] == [RequestStatus.SENT] * 3 + [
            RequestStatus.RATE_LIMITED,
            RequestStatus.UNKNOWN_EMAIL,
        ]
        for request in requests:
            assert len(request.request_id) == 32
            assert uuid.UUID(hex=request.request_id).version == 4


class TestPurgeExpired:
    def test_keeps_requests_within_the_rate_limit_window(self, service, store, clock):
        request = service.request_login("jane@example.com", link_for=_link)
        clock.advance(30 * 60)

        assert service.purge_expired() == 0
        assert store.get(request.request_id) is not None

    def test_deletes_requests_past_the_longest_window(self, service, store, clock):
        request = service.request_login("jane@example.com", link_for=_link)
        clock.advance(15 * 60 + 60 * 60 + 1)

        assert service.purge_expired() == 1
        assert store.get(request.request_id) is None


class TestStoreConsume:
    def _request(self) -> LoginTokenRequest:
        return LoginTokenRequest(
            id="r1",
            user_id="u1",
            email_hash="e",
            link_hash="l",
            code_hash="c",
            created_at=START,
            expires_at=START + timedelta(minutes=15),
        )

    def test_consume_succeeds_once_under_concurrency(self, store):
        store.add(self._request())
        results: list[bool] = []

        def consume() -> None:
            results.append(store.consume("r1", START))

        threads = [threading.Thread(target=consume) for _ in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert results.count(True) == 1

    def test_consume_fails_after_expiry(self, store):
        store.add(self._request())

        assert not store.consume("r1", START + timedelta(minutes=15))

    def test_times_round_trip_as_utc(self, store):
        store.add(self._request())
        stored = store.get("r1")

        assert stored is not None
        assert stored.created_at == START
        assert stored.created_at.tzinfo is not None


class TestLoggingSender:
    def test_writes_code_and_link_to_the_log(self, users, caplog):
        user = users.get_user_by_username("jane")
        message = LoginTokenMessage(
            user=user, email="jane@example.com", link=_link("abc"), code="123456", expires_at=START
        )

        with caplog.at_level("WARNING"):
            LoggingLoginTokenSender().send_login_token(message)

        assert "123456" in caplog.text
        assert _link("abc") in caplog.text
        assert "jane@example.com" in caplog.text
