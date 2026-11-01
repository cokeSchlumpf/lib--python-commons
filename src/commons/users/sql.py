"""
SQL-based implementation of the UsersRepository.

This module provides ``SQLUsersRepository``, a concrete implementation of
``UsersRepository`` that persists users, roles, and permissions to a SQL
database using SQLAlchemy and SQLModel.
"""

import logging
from typing import Any, cast

from sqlalchemy import CursorResult, Engine, delete, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, selectinload, sessionmaker
from sqlalchemy.sql.elements import ColumnElement
from sqlmodel import SQLModel, col  # type: ignore

from commons.users.repository import (
    DefaultRoleAssignment,
    PasswordHasher,
    PasswordVerifier,
    UsersRepository,
)
from commons.users.user import (
    Permission,
    RegisteredUser,
    Role,
    RoleAssignment,
    RolePermission,
    Scope,
    _normalize_path,
)

LOG = logging.getLogger(__name__)


class SQLUsersRepository(UsersRepository):
    """
    SQL database implementation of UsersRepository using SQLAlchemy/SQLModel.

    This repository persists users, roles, permissions, and role assignments
    to a SQL database. It automatically creates the required tables on
    initialization if they don't exist.

    Existing tables are not migrated: a database created before commons 1.4 (without
    ``registered_users.locale``) or before commons 1.2 (without ``roles.is_default_role``
    and the unique role assignments) must be recreated.

    Supported databases include SQLite, PostgreSQL, MySQL, and any other
    database supported by SQLAlchemy.

    Args:
        engine: SQLAlchemy Engine connected to the database.
        default_roles: Roles defined in code. They are synced into the database on
            creation (marked as default roles, with exactly these permissions); default
            roles no longer listed are deleted with their assignments. They can't be
            changed or deleted at runtime. See "Default Roles" in [`commons.users`][commons.users].
        anonymous_default_permissions: Role assignments automatically applied
            to anonymous (unauthenticated) users.
        authenticated_default_permissions: Role assignments automatically applied
            to authenticated users without local accounts.
        registered_default_permissions: Role assignments automatically applied
            to all registered users (in addition to their individual assignments).
        password_hasher: Custom password hashing function. Defaults to bcrypt.
        password_verifier: Custom password verification function. Defaults to bcrypt.

    Example::

        from sqlalchemy import create_engine
        from commons.users import SQLUsersRepository, Role

        # Create with SQLite
        engine = create_engine("sqlite:///users.db")
        repo = SQLUsersRepository(engine)

        # Create with PostgreSQL and default roles
        engine = create_engine("postgresql://user:pass@localhost/db")
        viewer_role = Role.create("viewer", ["/read"])
        repo = SQLUsersRepository(
            engine,
            default_roles=[viewer_role],
            registered_default_permissions=[DefaultRoleAssignment(scope="/", role="viewer")],
        )

    See Also:
        UsersRepository: Abstract base class defining the interface.
    """

    def __init__(
        self,
        engine: Engine,
        default_roles: list[Role] | None = None,
        anonymous_default_permissions: list[DefaultRoleAssignment] | None = None,
        authenticated_default_permissions: list[DefaultRoleAssignment] | None = None,
        registered_default_permissions: list[DefaultRoleAssignment] | None = None,
        password_hasher: PasswordHasher | None = None,
        password_verifier: PasswordVerifier | None = None,
    ):
        super().__init__(
            default_roles,
            anonymous_default_permissions,
            authenticated_default_permissions,
            registered_default_permissions,
            password_hasher,
            password_verifier,
        )
        self._engine = engine
        self._create_session = sessionmaker(bind=self._engine)

        SQLModel.metadata.create_all(self._engine, checkfirst=True)

        for role in self.default_roles:
            role.is_default_role = True
            for permission in role.permissions:
                permission.name = _normalize_path("permission", permission.name)

        try:
            self._sync_default_roles()
        except IntegrityError:
            # Another process (e.g. a second worker starting) inserted the same rows at the same moment;
            # running again finds them and only updates them.
            self._sync_default_roles()

    def add_assignment(self, user: RegisteredUser | str, scope: str, role: str) -> RoleAssignment:
        if isinstance(user, str):
            user = self.get_user_by_username(user)
        scope = _normalize_path("scope", scope)
        self.get_role_by_name(role)  # KeyError for an unknown role, before anything is written

        with self._create_session() as session:
            existing = session.execute(
                select(RoleAssignment).where(
                    RoleAssignment.user_id == user.id,  # type: ignore[arg-type]
                    RoleAssignment.scope_name == scope,  # type: ignore[arg-type]
                    RoleAssignment.role_name == role,  # type: ignore[arg-type]
                )
            ).scalar_one_or_none()
            if existing:
                session.expunge(existing)
                return existing

            existing_scope = session.execute(
                select(Scope).where(Scope.name == scope)  # type: ignore[arg-type]
            ).scalar_one_or_none()
            if not existing_scope:
                session.add(Scope(name=scope))

            assignment = RoleAssignment(
                scope_name=scope,
                role_name=role,
                user_id=user.id,
            )
            session.add(assignment)
            session.commit()
            session.refresh(assignment)
            session.expunge(assignment)
            return assignment

    def delete_role(self, role: Role | str) -> None:
        self._reject_default_role(role)

        with self._create_session() as session:
            if isinstance(role, str):
                db_role = session.execute(
                    select(Role).where(Role.name == role)  # type: ignore[arg-type]
                ).scalar_one_or_none()
            else:
                db_role = session.merge(role)

            if db_role:
                session.delete(db_role)
                session.commit()

    def delete_user(self, user: RegisteredUser | str) -> None:
        with self._create_session() as session:
            if isinstance(user, str):
                user = self.get_user_by_username(user)

            db_user = session.merge(user)
            session.delete(db_user)
            session.commit()

    def find_user_by_email(self, email: str) -> RegisteredUser | None:
        with self._create_session() as session:
            results = list(
                session.execute(
                    select(RegisteredUser).where(
                        func.lower(RegisteredUser.email_) == email.lower()  # type: ignore[arg-type]
                    )
                )
                .scalars()
                .all()
            )
            if len(results) > 1:
                raise ValueError(f"Multiple users found with email `{email}`.")
            for user in results:
                session.expunge(user)
            return results[0] if results else None

    def find_user_by_id(self, user_id: str) -> RegisteredUser | None:
        with self._create_session() as session:
            result = session.execute(
                select(RegisteredUser).where(RegisteredUser.id_ == user_id)  # type: ignore[arg-type]
            ).scalar_one_or_none()
            if result:
                session.expunge(result)
            return result

    def find_user_by_username(self, username: str) -> RegisteredUser | None:
        with self._create_session() as session:
            result = session.execute(
                select(RegisteredUser).where(RegisteredUser.username_ == username)  # type: ignore[arg-type]
            ).scalar_one_or_none()
            if result:
                session.expunge(result)
            return result

    def get_role_assignments(self, user: RegisteredUser | str) -> list[RoleAssignment]:
        with self._create_session() as session:
            if isinstance(user, str):
                user = self.get_user_by_username(user)

            results = list(
                session.execute(
                    select(RoleAssignment).where(RoleAssignment.user_id == user.id)  # type: ignore[arg-type]
                )
                .scalars()
                .all()
            )
            for ra in results:
                session.expunge(ra)
            return results

    def list_assignments(self, scope: str) -> list[RoleAssignment]:
        scope = _normalize_path("scope", scope)
        with self._create_session() as session:
            results = list(
                session.execute(
                    select(RoleAssignment)
                    .where(_in_subtree(col(RoleAssignment.scope_name), scope))
                    .options(
                        selectinload(RoleAssignment.user),  # type: ignore[arg-type]
                        selectinload(RoleAssignment.role),  # type: ignore[arg-type]
                        selectinload(RoleAssignment.scope),  # type: ignore[arg-type]
                    )
                )
                .scalars()
                .all()
            )
            session.expunge_all()
            return results

    def list_roles(self) -> list[Role]:
        with self._create_session() as session:
            results = list(session.execute(select(Role)).scalars().all())
            for role in results:
                session.expunge(role)
            return results

    def remove_assignment(self, assignment: RoleAssignment | str) -> None:
        with self._create_session() as session:
            if isinstance(assignment, str):
                db_assignment = session.execute(
                    select(RoleAssignment).where(RoleAssignment.id == assignment)  # type: ignore[arg-type]
                ).scalar_one_or_none()
            else:
                db_assignment = session.merge(assignment)

            if db_assignment:
                session.delete(db_assignment)
                session.commit()

    def remove_assignments(self, scope: str) -> int:
        scope = _normalize_path("scope", scope)
        with self._create_session() as session:
            result = session.execute(delete(RoleAssignment).where(_in_subtree(col(RoleAssignment.scope_name), scope)))
            still_used = select(col(RoleAssignment.scope_name))
            session.execute(
                delete(Scope).where(_in_subtree(col(Scope.name), scope), col(Scope.name).not_in(still_used))
            )
            session.commit()
            return cast(CursorResult[Any], result).rowcount

    def upsert_role(self, role: Role) -> Role:
        self._reject_default_role(role)

        for permission in role.permissions:
            permission.name = _normalize_path("permission", permission.name)

        with self._create_session() as session:
            # Built in the session instead of merging the given objects: merging cascades the role's
            # permissions, and stored ones would be inserted a second time.
            permissions = [session.get(Permission, p.name) or Permission(name=p.name) for p in role.permissions]
            db_role = session.get(Role, role.name)
            if db_role is None:
                db_role = Role(name=role.name, permissions=permissions)
                session.add(db_role)
            else:
                db_role.permissions = permissions

            session.commit()
            session.refresh(db_role)
            session.expunge(db_role)
            return db_role

    def upsert_user(self, user: RegisteredUser) -> RegisteredUser:
        with self._create_session() as session:
            merged_user = session.merge(user)
            session.commit()
            session.refresh(merged_user)
            session.expunge(merged_user)
            return merged_user

    def _reject_default_role(self, role: Role | str) -> None:
        name = role if isinstance(role, str) else role.name
        if (isinstance(role, Role) and role.is_default_role) or any(r.name == name for r in self.default_roles):
            raise ValueError(f"Role `{name}` is a default role; it can only be changed in the code (`default_roles`).")

    def _sync_default_roles(self) -> None:
        """
        Make the database match ``default_roles``, the code being the source of truth.

        Every default role is stored with exactly the permissions of the code, marked as
        default role; a role of the same name created by the app is taken over, keeping
        its assignments. Roles marked as default role that are no longer in the code are
        deleted together with their assignments. Roles of the app are not touched.
        """
        names = {role.name for role in self.default_roles}

        with self._create_session() as session:
            for role in self.default_roles:
                permissions = [session.get(Permission, p.name) or Permission(name=p.name) for p in role.permissions]
                db_role = session.get(Role, role.name)
                if db_role is None:
                    session.add(Role(name=role.name, is_default_role=True, permissions=permissions))
                else:
                    db_role.is_default_role = True
                    db_role.permissions = permissions

            removed = session.execute(
                select(col(Role.name)).where(col(Role.is_default_role), col(Role.name).not_in(names))
            ).scalars()
            for name in list(removed):
                result = session.execute(delete(RoleAssignment).where(col(RoleAssignment.role_name) == name))
                session.execute(delete(RolePermission).where(col(RolePermission.role_name) == name))
                session.execute(delete(Role).where(col(Role.name) == name))
                LOG.info(
                    "Deleted default role `%s`, which is no longer in the code, with %d assignment(s).",
                    name,
                    cast(CursorResult[Any], result).rowcount,
                )

            session.commit()

    def _find_role_by_name(self, name: str) -> Role | None:
        with self._create_session() as session:
            result = session.execute(
                select(Role).where(Role.name == name)  # type: ignore[arg-type]
            ).scalar_one_or_none()
            if result:
                session.expunge(result)
            return result


def _in_subtree(column: Mapped[str], scope: str) -> ColumnElement[bool]:
    """The rows whose scope is ``scope`` or below it; ``scope`` is normalized, so it holds neither ``%`` nor ``_``."""
    if scope == "/":
        return column.is_not(None)
    return or_(column == scope, column.like(scope + "/%"))
