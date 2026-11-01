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
   SQLModel table class. Created via ``RegisteredUser.create()``. A registered user
   may have no password (``password_hash`` is ``None``): they can't sign in with a
   password, only by other means such as an email link or code
   ([`commons.users.login_tokens`][commons.users.login_tokens]).

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
  This is the primary mechanism for granting permissions to users. A user has a role
  on a scope at most once; the same role on another scope is a separate assignment.
  ``list_assignments(scope)`` and ``remove_assignments(scope)`` work on a scope and
  every scope below it (e.g. all roles in a tenant).

A role on a scope applies to every scope below it, so a typical multi-tenant setup is
an ``admin`` role on ``"/app"`` for global admins and a ``tenant-admin`` role on
``"/app/tenants/<tenant-id>"`` for the admins of one tenant.

Paths
-----
Scope and permission paths are normalized to one spelling wherever they enter
(assigning, defining roles, checking): ``"/app/"`` and ``"app"`` are ``"/app"``,
``"/app//x"`` is ``"/app/x"``, ``"/foo/Foo Bar"`` is ``"/foo/foo-bar"``; letters are
lowercased, accents removed, other characters become ``-``, and dashes (also double
ones, ``"/lib--python-commons"``) are kept. Paths whose meaning normalizing would
change raise ``ValueError``: segments ``.`` and ``..``, segments that are empty after
normalizing, and paths without segments other than the root ``"/"`` (e.g. ``""``).

Because different spellings become one scope, ids that differ only in case or special
characters share their roles (``Tenant_A`` and ``tenant-a``): build scopes from
generated ids (``commons.id_operators.new_id``), not from names.

Default Roles
-------------
Roles passed as ``default_roles`` to the repository are defined in code. They are
synced into the database when the repository is created: stored with exactly the
permissions of the code and marked as default role (``Role.is_default_role``), so they
can be assigned like any other role; a role of the same name created by the app is
taken over. A default role removed from the code is deleted on the next start,
together with its assignments. Default roles can't be changed or deleted at runtime
(``upsert_role()`` and ``delete_role()`` raise ``ValueError``); apps should show them as
not editable.

Repository Pattern
------------------
User operations are performed through repository classes:

- **UsersRepository**: Abstract base class defining the interface for user management,
  authentication, and permission checking.

- **SQLUsersRepository**: Concrete implementation using SQLAlchemy/SQLModel for
  database persistence.

Command Line
------------
``python -m commons.users hash-password`` prints a bcrypt hash for a password, to be
used as ``password_hash`` of users defined in the settings (see
``commons.settings.StandardUser``).

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
