from datetime import UTC, datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine

from commons.users import RegisteredUser, Role, SQLUsersRepository
from commons.users.login_tokens import (
    InMemoryLoginTokenStore,
    LoginTokenMessage,
    LoginTokenService,
    LoginTokenSettings,
    RedeemStatus,
    RequestStatus,
)
from commons.users.repository import DefaultRoleAssignment

START = datetime(2026, 11, 2, 9, 0, tzinfo=UTC)


@pytest.fixture
def repo(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'users.db'}")
    repo = SQLUsersRepository(engine, default_roles=[Role.create("editor", ["/write"])])
    yield repo
    engine.dispose()


def _jane(repo: SQLUsersRepository, **kwargs) -> RegisteredUser:
    return repo.upsert_user(
        RegisteredUser.create(
            "jane", repo.hash_password("secret"), "Jane Doe", email="jane@example.com", **kwargs
        )
    )


class TestCanSignIn:
    def test_active_without_limit_by_default(self):
        user = RegisteredUser.create("jane", None, "Jane Doe")

        assert user.is_active and user.valid_from is None and user.valid_until is None
        assert user.can_sign_in(START)

    def test_inactive_user_cannot_sign_in(self):
        assert not RegisteredUser.create("jane", None, "Jane Doe", is_active=False).can_sign_in(START)

    @pytest.mark.parametrize(
        ("at", "expected"),
        [
            (START - timedelta(seconds=1), False),
            (START, True),
            (START + timedelta(days=7) - timedelta(seconds=1), True),
            (START + timedelta(days=7), False),
        ],
    )
    def test_period_includes_start_and_excludes_end(self, at, expected):
        user = RegisteredUser.create("jane", None, "Jane Doe", valid_from=START, valid_until=START + timedelta(days=7))

        assert user.can_sign_in(at) is expected

    def test_open_bounds_do_not_limit(self):
        assert RegisteredUser.create("a", None, "A", valid_from=START).can_sign_in(START + timedelta(days=999))
        assert RegisteredUser.create("b", None, "B", valid_until=START).can_sign_in(START - timedelta(days=999))

    def test_other_time_zones_are_compared_in_utc(self):
        zurich = timezone(timedelta(hours=1))
        user = RegisteredUser.create("jane", None, "Jane Doe", valid_from=datetime(2026, 11, 2, 0, 0, tzinfo=zurich))

        assert user.valid_from == datetime(2026, 11, 1, 23, 0, tzinfo=UTC)
        assert user.can_sign_in(datetime(2026, 11, 1, 23, 30, tzinfo=UTC))


class TestStorage:
    def test_fields_are_stored_as_utc_and_can_be_changed(self, repo):
        _jane(repo, valid_from=START, valid_until=START + timedelta(days=1))

        user = repo.get_user_by_username("jane")
        assert user.is_active
        assert user.valid_from == START and user.valid_from.tzinfo is not None
        assert user.valid_until == START + timedelta(days=1)

        user.is_active = False
        user.valid_until = None
        repo.upsert_user(user)

        stored = repo.get_user_by_username("jane")
        assert not stored.is_active and stored.valid_until is None


class TestPermissions:
    def test_assigned_permission_only_while_user_can_sign_in(self, repo):
        user = _jane(repo)
        repo.add_assignment(user, "/app", "editor")
        assert repo.has_permission(user, "/app", "/write")

        user.is_active = False
        repo.upsert_user(user)

        assert not repo.has_permission(user, "/app", "/write")
        with pytest.raises(LookupError):
            repo.check_permission(user, "/app", "/write")

    def test_expired_user_has_no_default_permissions(self, tmp_path):
        engine = create_engine(f"sqlite:///{tmp_path / 'users.db'}")
        repo = SQLUsersRepository(
            engine,
            default_roles=[Role.create("reader", ["/read"])],
            registered_default_permissions=[DefaultRoleAssignment(scope="/", role="reader")],
        )
        user = _jane(repo, valid_until=datetime.now(UTC) - timedelta(days=1))

        assert not repo.has_permission(user, "/app", "/read")
        engine.dispose()


class TestAuthenticate:
    def test_inactive_user_is_not_authenticated(self, repo):
        _jane(repo, is_active=False)

        assert repo.authenticate("jane", "secret") is None

    def test_user_before_their_period_is_not_authenticated(self, repo):
        _jane(repo, valid_from=datetime.now(UTC) + timedelta(days=1))

        assert repo.authenticate("jane", "secret") is None

    def test_active_user_is_authenticated(self, repo):
        _jane(repo)

        assert repo.authenticate("jane", "secret") is not None


class _Sender:
    def __init__(self) -> None:
        self.messages: list[LoginTokenMessage] = []

    def send_login_token(self, message: LoginTokenMessage) -> None:
        self.messages.append(message)


class _Clock:
    def __init__(self) -> None:
        self.now = START

    def __call__(self) -> datetime:
        return self.now


class TestLoginTokens:
    def _service(self, repo, sender, clock) -> LoginTokenService:
        return LoginTokenService(
            repo,
            InMemoryLoginTokenStore(),
            secret_key="test-secret-key-0123456789",
            sender=sender,
            settings=LoginTokenSettings(),
            clock=clock,
        )

    def test_nothing_is_sent_to_an_inactive_user(self, repo):
        _jane(repo, is_active=False)
        sender = _Sender()

        result = self._service(repo, sender, _Clock()).request_login("jane@example.com", link_for=lambda t: t)

        assert result.status == RequestStatus.USER_INACTIVE
        assert sender.messages == []

    def test_nothing_is_sent_outside_the_period(self, repo):
        _jane(repo, valid_until=START)
        sender = _Sender()

        result = self._service(repo, sender, _Clock()).request_login("jane@example.com", link_for=lambda t: t)

        assert result.status == RequestStatus.USER_INACTIVE
        assert sender.messages == []

    def test_code_requested_before_cannot_be_redeemed_after_deactivation(self, repo):
        user = _jane(repo)
        sender = _Sender()
        service = self._service(repo, sender, _Clock())
        request = service.request_login("jane@example.com", link_for=lambda t: t)
        user.is_active = False
        repo.upsert_user(user)

        result = service.redeem_code(request.request_id, sender.messages[-1].code)

        assert result.status == RedeemStatus.USER_INACTIVE
        assert result.user is None

    def test_link_cannot_be_redeemed_after_the_period_ends(self, repo):
        _jane(repo, valid_until=START + timedelta(minutes=1))
        sender = _Sender()
        clock = _Clock()
        service = self._service(repo, sender, clock)
        service.request_login("jane@example.com", link_for=lambda t: t)
        clock.now = START + timedelta(minutes=1)

        result = service.redeem_link(sender.messages[-1].link)

        assert result.status == RedeemStatus.USER_INACTIVE

    def test_active_user_can_redeem(self, repo):
        _jane(repo, valid_from=START)
        sender = _Sender()
        service = self._service(repo, sender, _Clock())
        request = service.request_login("jane@example.com", link_for=lambda t: t)

        assert service.redeem_code(request.request_id, sender.messages[-1].code).status == RedeemStatus.OK


class TestListUsers:
    def test_lists_all_users_by_username(self, repo):
        for name in ("zoe", "adam", "mia"):
            repo.upsert_user(RegisteredUser.create(name, None, name.title(), is_active=name != "mia"))

        assert [u.username for u in repo.list_users()] == ["adam", "mia", "zoe"]

    def test_empty(self, repo):
        assert repo.list_users() == []
