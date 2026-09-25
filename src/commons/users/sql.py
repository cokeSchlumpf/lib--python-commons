"""
SQL-based implementation of the UsersRepository.

This module provides ``SQLUsersRepository``, a concrete implementation of
``UsersRepository`` that persists users, roles, and permissions to a SQL
database using SQLAlchemy and SQLModel.
"""

from sqlalchemy import Engine, select
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel  # type: ignore

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
    Scope,
)


class SQLUsersRepository(UsersRepository):
    """
    SQL database implementation of UsersRepository using SQLAlchemy/SQLModel.

    This repository persists users, roles, permissions, and role assignments
    to a SQL database. It automatically creates the required tables on
    initialization if they don't exist.

    Supported databases include SQLite, PostgreSQL, MySQL, and any other
    database supported by SQLAlchemy.

    Args:
        engine: SQLAlchemy Engine connected to the database.
        default_roles: Predefined roles available without database lookup.
            These roles are checked first when looking up roles by name.
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

    def add_assignment(self, user: RegisteredUser | str, scope: str, role: str) -> RoleAssignment:
        with self._create_session() as session:
            if isinstance(user, str):
                user = self.get_user_by_username(user)

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

    def upsert_role(self, role: Role) -> Role:
        with self._create_session() as session:
            for permission in role.permissions:
                existing_perm = session.execute(
                    select(Permission).where(Permission.name == permission.name)  # type: ignore[arg-type]
                ).scalar_one_or_none()
                if not existing_perm:
                    session.add(permission)

            merged_role = session.merge(role)
            session.commit()
            session.refresh(merged_role)
            session.expunge(merged_role)
            return merged_role

    def upsert_user(self, user: RegisteredUser) -> RegisteredUser:
        with self._create_session() as session:
            merged_user = session.merge(user)
            session.commit()
            session.refresh(merged_user)
            session.expunge(merged_user)
            return merged_user

    def _find_role_by_name(self, name: str) -> Role | None:
        with self._create_session() as session:
            result = session.execute(
                select(Role).where(Role.name == name)  # type: ignore[arg-type]
            ).scalar_one_or_none()
            if result:
                session.expunge(result)
            return result
