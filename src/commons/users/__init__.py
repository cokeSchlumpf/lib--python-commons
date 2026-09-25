"""
User management module providing authentication, authorization, and user identity classes.

This module implements a flexible user system with three levels of user identity
and a role-based access control (RBAC) system for permission management.

User Hierarchy
--------------
The module defines three concrete user types, all implementing the ``User`` protocol:

1. **AnonymousUser**: Represents unauthenticated visitors. Has a fixed ID of
   ``"__anonymous__"`` and no personal information. Use ``AnonymousUser.get()``
   to obtain the singleton instance.

2. **AuthenticatedUser**: Represents users authenticated via external systems
   (e.g., OAuth, SSO) who are not registered in the local database. Contains
   identity information (name, email) but no credentials. Created via
   ``AuthenticatedUser.create()``.

3. **RegisteredUser**: Represents users with local accounts stored in the database.
   Has credentials (username/password) and can have role assignments. This is a
   SQLModel table class. Created via ``RegisteredUser.create()``.

Permission System
-----------------
The RBAC system uses path-based scopes and permissions:

- **Permission**: A capability like ``"/read"`` or ``"/admin/delete"``. Permissions
  use hierarchical paths where ``"/admin"`` implies ``"/admin/delete"``.

- **Role**: A named collection of permissions (e.g., "editor" with ``["/read", "/write"]``).
  Roles are linked to permissions via the ``RolePermission`` junction table.

- **Scope**: A resource boundary like ``"/projects/my-project"``. Scopes use hierarchical
  paths where ``"/projects"`` contains ``"/projects/my-project"``.

- **RoleAssignment**: Links a ``RegisteredUser`` to a ``Role`` within a ``Scope``.
  This is the primary mechanism for granting permissions to users.

Repository Pattern
------------------
User operations are performed through repository classes:

- **UsersRepository**: Abstract base class defining the interface for user management,
  authentication, and permission checking.

- **SQLUsersRepository**: Concrete implementation using SQLAlchemy/SQLModel for
  database persistence.

Example Usage
-------------
::

    from sqlalchemy import create_engine
    from commons.users import SQLUsersRepository, RegisteredUser, Role

    # Create repository
    engine = create_engine("sqlite:///users.db")
    repo = SQLUsersRepository(engine)

    # Create a role with permissions
    admin_role = Role.create("admin", ["/read", "/write", "/admin"])
    repo.upsert_role(admin_role)

    # Create a user
    user = RegisteredUser.create(
        username="john.doe",
        password_hash=repo.hash_password("secret"),
        display_name="John Doe",
        firstname="John",
        lastname="Doe",
        email="john@example.com",
    )
    repo.upsert_user(user)

    # Assign role to user
    repo.add_assignment(user, "/projects/alpha", "admin")

    # Check permission
    if repo.has_permission(user, "/projects/alpha", "/write"):
        print("User can write!")
"""

from .repository import UsersRepository
from .sql import SQLUsersRepository
from .user import (
    User,
    AnonymousUser,
    AuthenticatedUser,
    RegisteredUser,
    Role,
    RoleAssignment,
    RolePermission,
    SystemUser,
)

__all__ = [
    "AnonymousUser",
    "AuthenticatedUser",
    "RegisteredUser",
    "Role",
    "RoleAssignment",
    "RolePermission",
    "SystemUser",
    "SQLUsersRepository",
    "User",
    "UsersRepository",
]
