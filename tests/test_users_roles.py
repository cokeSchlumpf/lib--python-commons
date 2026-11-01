import pytest
from sqlalchemy import create_engine, event

from commons.settings import RoleAssignmentConfig
from commons.users import AnonymousUser, RegisteredUser, Role, RoleAssignment, SQLUsersRepository
from commons.users.repository import DefaultRoleAssignment
from commons.users.user import _normalize_path

TENANT_A = "01a1970a-1797-70d6-90d1-d278a4c07797"
TENANT_B = "01a1970a-1797-70d6-90d1-d278a4c07798"


@pytest.fixture(params=["fk-off", "fk-on"])
def engine(request, tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'users.db'}")
    if request.param == "fk-on":
        event.listen(engine, "connect", lambda connection, _: connection.execute("PRAGMA foreign_keys=ON"))
    yield engine
    engine.dispose()


@pytest.fixture
def repo(engine):
    repo = SQLUsersRepository(engine)
    repo.upsert_role(Role.create("admin", ["/"]))
    repo.upsert_role(Role.create("tenant-admin", ["/read", "/write", "/manage-users"]))
    repo.upsert_role(Role.create("viewer", ["/read"]))
    return repo


def _user(repo: SQLUsersRepository, username: str) -> RegisteredUser:
    return repo.upsert_user(RegisteredUser.create(username, None, username))


class TestNormalizePath:
    @pytest.mark.parametrize(
        ("path", "expected"),
        [
            ("/", "/"),
            ("/app", "/app"),
            ("/app/", "/app"),
            ("app", "/app"),
            ("/app//x", "/app/x"),
            ("/foo/Foo Bar", "/foo/foo-bar"),
            ("/lib--python-commons", "/lib--python-commons"),
            ("/a--b/c", "/a--b/c"),
            ("/app/tenants/Tenant_A", "/app/tenants/tenant-a"),
            ("/über", "/uber"),
            (f"/app/tenants/{TENANT_A.upper()}", f"/app/tenants/{TENANT_A}"),
            ("read", "/read"),
        ],
    )
    def test_normalizes(self, path, expected):
        assert _normalize_path("scope", path) == expected

    @pytest.mark.parametrize("path", ["/a/../b", "/a/./b", "/..", "", "//", "/ ", "/!!!"])
    def test_rejects_what_would_change_the_meaning(self, path):
        with pytest.raises(ValueError, match="Invalid scope"):
            _normalize_path("scope", path)


class TestPathsAtEntryPoints:
    def test_role_create_normalizes_permissions(self):
        role = Role.create("editor", ["/Read", "write/", "/read"])

        assert [p.name for p in role.permissions] == ["/read", "/write"]

    def test_upsert_role_normalizes_permissions(self, repo):
        role = Role.create("editor", ["/read"])
        role.permissions[0].name = "/Docs/Read/"

        stored = repo.upsert_role(role)

        assert [p.name for p in stored.permissions] == ["/docs/read"]

    def test_add_assignment_stores_the_normalized_scope(self, repo):
        user = _user(repo, "jane")

        assignment = repo.add_assignment(user, "/App/Tenants/Tenant A/", "viewer")

        assert assignment.scope_name == "/app/tenants/tenant-a"

    def test_add_assignment_rejects_dot_segments(self, repo):
        user = _user(repo, "jane")

        with pytest.raises(ValueError, match="Invalid scope"):
            repo.add_assignment(user, f"/app/tenants/{TENANT_A}/../{TENANT_B}", "viewer")

        assert repo.get_role_assignments(user) == []

    def test_check_in_another_spelling_than_the_assignment(self, repo):
        user = _user(repo, "jane")
        repo.add_assignment(user, "/app/foo-bar", "viewer")

        assert repo.has_permission(user, "/App/Foo Bar/", "Read")
        assert repo.role_has_permission("/APP", "viewer", "/app/x", "/READ/")

    def test_checks_reject_dot_segments(self, repo):
        user = _user(repo, "jane")

        with pytest.raises(ValueError, match="Invalid scope"):
            repo.has_permission(user, "/app/..", "/read")
        with pytest.raises(ValueError, match="Invalid permission"):
            repo.check_permission(user, "/app", "/read/..")

    def test_default_role_assignment_normalizes_scope(self):
        assert DefaultRoleAssignment(scope="/Public/", role="viewer").scope == "/public"

    def test_settings_role_assignment_normalizes_scope(self):
        assert RoleAssignmentConfig(scope="App/Tenants/", role="viewer").scope == "/app/tenants"

        with pytest.raises(ValueError, match="Invalid scope"):
            RoleAssignmentConfig(scope="/app/../x", role="viewer")


class TestContainment:
    def test_the_dot_dot_bypass_of_the_intent_is_closed(self, repo):
        user = _user(repo, "tenant-a-admin")
        repo.add_assignment(user, f"/app/tenants/{TENANT_A}", "tenant-admin")

        with pytest.raises(ValueError):
            repo.has_permission(user, f"/app/tenants/{TENANT_A}/../{TENANT_B}", "/write")

    def test_tenant_admin_stays_in_their_tenant(self, repo):
        user = _user(repo, "tenant-a-admin")
        repo.add_assignment(user, f"/app/tenants/{TENANT_A}", "tenant-admin")

        assert repo.has_permission(user, f"/app/tenants/{TENANT_A}", "/write")
        assert repo.has_permission(user, f"/app/tenants/{TENANT_A}/cases/1", "/write")
        assert not repo.has_permission(user, f"/app/tenants/{TENANT_B}", "/write")
        assert not repo.has_permission(user, "/app", "/write")
        assert not repo.has_permission(user, f"/app/tenants/{TENANT_A}x", "/write")

    def test_global_admin_reaches_every_tenant(self, repo):
        user = _user(repo, "global-admin")
        repo.add_assignment(user, "/app", "admin")

        assert repo.has_permission(user, f"/app/tenants/{TENANT_A}", "/write")
        assert repo.has_permission(user, "/app", "/anything/at/all")
        assert not repo.has_permission(user, "/other-app", "/read")

    def test_permissions_are_contained_by_segment(self, repo):
        assert repo.role_has_permission("/app", "tenant-admin", "/app", "/write/documents")
        assert not repo.role_has_permission("/app", "tenant-admin", "/app", "/writer")

    def test_root_scope_contains_everything(self, repo):
        assert repo.role_has_permission("/", "viewer", "/any/scope", "/read")


class TestAssignments:
    def test_assigning_twice_returns_the_first_assignment(self, repo):
        user = _user(repo, "jane")

        first = repo.add_assignment(user, "/app", "viewer")
        second = repo.add_assignment(user, "/App/", "viewer")

        assert second.id == first.id
        assert len(repo.get_role_assignments(user)) == 1

    def test_same_role_on_a_scope_and_below_it_are_two_assignments(self, repo):
        user = _user(repo, "jane")
        on_app = repo.add_assignment(user, "/app", "admin")
        repo.add_assignment(user, "/app/foo/bar", "admin")

        assert len(repo.get_role_assignments(user)) == 2

        repo.remove_assignment(on_app)

        assert repo.has_permission(user, "/app/foo/bar", "/write")
        assert not repo.has_permission(user, "/app", "/write")

    def test_other_roles_on_the_same_scope_are_separate(self, repo):
        user = _user(repo, "jane")
        repo.add_assignment(user, "/app", "viewer")
        repo.add_assignment(user, "/app", "admin")

        assert {a.role_name for a in repo.get_role_assignments(user)} == {"viewer", "admin"}

    def test_unknown_role_raises_and_writes_nothing(self, repo):
        user = _user(repo, "jane")

        with pytest.raises(KeyError, match="no-such-role"):
            repo.add_assignment(user, "/app", "no-such-role")

        assert repo.get_role_assignments(user) == []
        assert repo.list_assignments("/") == []


class TestFailClosed:
    def test_assignment_to_a_missing_role_is_skipped_and_logged(self, repo, monkeypatch, caplog):
        user = _user(repo, "jane")
        repo.add_assignment(user, "/app", "viewer")
        stored = repo.get_role_assignments(user)
        # The state a vanished role leaves behind (e.g. deleted while foreign keys were off).
        vanished = RoleAssignment(scope_name="/app", role_name="vanished", user_id=user.id)
        monkeypatch.setattr(repo, "get_role_assignments", lambda _user: [vanished, *stored])

        assert repo.has_permission(user, "/app", "/read")  # the viewer assignment still counts
        assert not repo.has_permission(user, "/app", "/write")  # the vanished role grants nothing
        assert "Role `vanished` on scope `/app` doesn't exist" in caplog.text

    def test_default_permission_with_a_missing_role_grants_nothing(self, engine, caplog):
        repo = SQLUsersRepository(
            engine, anonymous_default_permissions=[DefaultRoleAssignment(scope="/public", role="missing")]
        )

        assert not repo.has_permission(AnonymousUser.get(), "/public", "/read")
        assert "Role `missing` on scope `/public` doesn't exist" in caplog.text


class TestByScope:
    @pytest.fixture
    def tenants(self, repo):
        alice, bob, carol = _user(repo, "alice"), _user(repo, "bob"), _user(repo, "carol")
        repo.add_assignment(alice, f"/app/tenants/{TENANT_A}", "tenant-admin")
        repo.add_assignment(bob, f"/app/tenants/{TENANT_A}/cases/1", "viewer")
        repo.add_assignment(bob, f"/app/tenants/{TENANT_B}", "viewer")
        repo.add_assignment(carol, "/app", "admin")
        repo.add_assignment(carol, f"/app/tenants/{TENANT_A}x", "viewer")
        return repo

    def test_lists_the_scope_and_below_with_users_loaded(self, tenants):
        assignments = tenants.list_assignments(f"/app/tenants/{TENANT_A}")

        assert sorted((a.user.username, a.role.name, a.scope.name) for a in assignments) == [
            ("alice", "tenant-admin", f"/app/tenants/{TENANT_A}"),
            ("bob", "viewer", f"/app/tenants/{TENANT_A}/cases/1"),
        ]

    def test_lists_everything_from_the_root(self, tenants):
        assert len(tenants.list_assignments("/")) == 5

    def test_removes_the_scope_and_below(self, tenants):
        removed = tenants.remove_assignments(f"/App/Tenants/{TENANT_A}/")

        assert removed == 2
        assert tenants.list_assignments(f"/app/tenants/{TENANT_A}") == []
        assert {a.user.username for a in tenants.list_assignments("/")} == {"bob", "carol"}
        assert len(tenants.list_assignments("/")) == 3

    def test_removes_unused_scope_entries(self, tenants, engine):
        from sqlalchemy import select
        from sqlalchemy.orm import Session

        from commons.users.user import Scope

        tenants.remove_assignments(f"/app/tenants/{TENANT_A}")

        with Session(engine) as session:
            names = set(session.execute(select(Scope.name)).scalars())  # type: ignore[call-overload]
        assert names == {"/app", f"/app/tenants/{TENANT_B}", f"/app/tenants/{TENANT_A}x"}
