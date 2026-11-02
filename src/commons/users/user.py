"""
User identity and RBAC model classes.

This module defines the core user types and role-based access control (RBAC) entities
used throughout the application. All user types implement the ``User`` protocol,
allowing them to be used interchangeably in permission checks.

Classes:
    User: Protocol defining the common interface for all user types.
    AnonymousUser: Represents unauthenticated visitors.
    AuthenticatedUser: Represents externally authenticated users without local accounts.
    RegisteredUser: Represents users with local database accounts.
    Permission: A capability that can be granted via roles.
    Role: A named collection of permissions.
    Scope: A resource boundary for permission assignments.
    RoleAssignment: Links a user to a role within a scope.
    RolePermission: Junction table linking roles to permissions.
"""

import re
from datetime import datetime, timezone
from typing import Literal, Protocol, runtime_checkable
from pydantic import BaseModel, ConfigDict, field_validator
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, PrimaryKeyConstraint, String, Unicode, UniqueConstraint
from sqlmodel import Field, Relationship, SQLModel  # type: ignore

from commons.id_operators import new_id
from commons.string_operators import remove_accents


def _normalize_path(kind: str, value: str) -> str:
    """
    Normalize a scope or permission path to its one canonical spelling, or raise.

    Empty segments (leading, trailing and double slashes) are dropped and a leading
    ``/`` is added. In each segment, accents are removed, letters are lowercased, and
    every run of characters other than ``a-z``, ``0-9`` and ``-`` becomes one ``-``,
    without leading or trailing ``-``; dashes already in a segment are kept, so double
    dashes stay. Examples: ``"/app/"`` and ``"app"`` become ``"/app"``, ``"/foo/Foo Bar"``
    becomes ``"/foo/foo-bar"``, ``"/lib--python-commons"`` stays as it is.

    Normalizing never changes which scope is meant, so these raise instead: a segment
    ``.`` or ``..``, a segment that is empty after normalizing (e.g. ``"/!!!"``), and a
    path without segments other than the literal ``"/"`` (e.g. ``""``, ``"//"``): only
    ``"/"`` means the root.

    Args:
        kind: What the path is (``"scope"`` or ``"permission"``), for the error message.
        value: The path to normalize.

    Returns:
        The normalized path.

    Raises:
        ValueError: If the path can't be normalized without changing its meaning.
    """
    if value == "/":
        return "/"

    segments = []
    for raw in value.split("/"):
        if raw == "":
            continue  # leading, trailing or double slash
        if raw in (".", ".."):
            raise ValueError(f"Invalid {kind} `{value}`: the segments `.` and `..` are not allowed.")
        segment = re.sub(r"[^a-z0-9-]+", "-", remove_accents(raw).lower()).strip("-")
        if not segment:
            raise ValueError(f"Invalid {kind} `{value}`: the segment `{raw}` is empty after normalizing.")
        segments.append(segment)

    if not segments:
        raise ValueError(f"Invalid {kind} `{value}`: only `/` means the root.")

    return "/" + "/".join(segments)


UserNameType = Literal["technical", "casual", "formal", "full"]
"""
Type of name format to return from the ``name()`` method.

Values:
    technical: Returns the technical identifier (username for RegisteredUser, id for others).
    casual: Returns the first name if available, otherwise display_name.
    formal: Returns "Lastname, Firstname" format if available, otherwise display_name.
    full: Returns "Firstname Lastname" format if available, otherwise display_name.
"""


@runtime_checkable
class User(Protocol):
    """
    Protocol defining the common interface for all user types.

    This protocol enables polymorphic handling of different user types
    (AnonymousUser, AuthenticatedUser, RegisteredUser) in permission checks
    and other operations.

    All concrete user classes implement this protocol, allowing code to work
    with any user type without knowing the specific implementation.

    Example::

        def greet_user(user: User) -> str:
            return f"Hello, {user.name('casual')}!"


        # Works with any user type
        greet_user(AnonymousUser.get())
        greet_user(AuthenticatedUser.create("John Doe"))
        greet_user(registered_user)
    """

    @property
    def id(self) -> str:
        """Unique identifier for the user."""
        ...

    @property
    def display_name(self) -> str:
        """Human-readable display name for the user."""
        ...

    @property
    def firstname(self) -> str | None:
        """User's first name, if available."""
        ...

    @property
    def lastname(self) -> str | None:
        """User's last name, if available."""
        ...

    @property
    def email(self) -> str | None:
        """User's email address, if available."""
        ...

    def name(self, type: UserNameType = "casual") -> str:
        """
        Get a formatted name for the user.

        Args:
            type: The name format to return. See ``UserNameType`` for options.

        Returns:
            The formatted name string.
        """
        ...


class SystemUser(BaseModel):
    """
    Represents a system itself.

    System users should be used when an applications does something autonomously (e.g., seeding, running background processes),
    which are not on behalf of other users.

    This class implements the ``User`` protocol.
    """

    id_: Literal["__system__"] = Field(default="__system__", validation_alias="id", serialization_alias="id")

    display_name_: str = Field(default="System", validation_alias="display_name", serialization_alias="display_name")

    @staticmethod
    def get() -> "SystemUser":
        """
        Get n SystemUser instance.

        Returns:
            A SystemUser with default values.
        """
        return SystemUser()

    @property
    def id(self) -> str:
        return self.id_

    @property
    def display_name(self) -> str:
        return self.display_name_

    @property
    def firstname(self) -> str | None:
        return None

    @property
    def lastname(self) -> str | None:
        return None

    @property
    def email(self) -> str | None:
        return None

    def name(self, type: UserNameType = "casual") -> str:
        """
        Get a formatted name for the anonymous user.

        Args:
            type: The name format (ignored for anonymous users).

        Returns:
            Always returns ``display_name`` since anonymous users have no personal info.
        """
        return self.display_name


class AnonymousUser(BaseModel):
    """
    Represents an unauthenticated user (visitor).

    Anonymous users have no personal information and a fixed identity. They are
    used to represent visitors who have not logged in. Permission checks for
    anonymous users use the repository's ``anonymous_default_permissions``.

    This class implements the ``User`` protocol.

    Attributes:
        id: Always ``"__anonymous__"``.
        display_name: Defaults to ``"Anonymous User"``.
        firstname: Always ``None``.
        lastname: Always ``None``.
        email: Always ``None``.

    Example::

        # Get the anonymous user instance
        anon = AnonymousUser.get()

        # Check permissions
        if repo.has_permission(anon, "/public", "/read"):
            show_public_content()
    """

    id_: Literal["__anonymous__"] = Field(default="__anonymous__", validation_alias="id", serialization_alias="id")

    display_name_: str = Field(
        default="Anonymous User", validation_alias="display_name", serialization_alias="display_name"
    )

    @staticmethod
    def get() -> "AnonymousUser":
        """
        Get an AnonymousUser instance.

        Returns:
            An AnonymousUser with default values.
        """
        return AnonymousUser()

    @property
    def id(self) -> str:
        return self.id_

    @property
    def display_name(self) -> str:
        return self.display_name_

    @property
    def firstname(self) -> str | None:
        return None

    @property
    def lastname(self) -> str | None:
        return None

    @property
    def email(self) -> str | None:
        return None

    def name(self, type: UserNameType = "casual") -> str:
        """
        Get a formatted name for the anonymous user.

        Args:
            type: The name format (ignored for anonymous users).

        Returns:
            Always returns ``display_name`` since anonymous users have no personal info.
        """
        return self.display_name


class AuthenticatedUser(BaseModel):
    """
    Represents a user authenticated via an external system without a local account.

    Authenticated users are typically created from external identity providers
    (OAuth, SSO, SAML, etc.). They have identity information but no local
    credentials. Permission checks use the repository's ``authenticated_default_permissions``.

    This class implements the ``User`` protocol.

    Use ``AuthenticatedUser.create()`` to construct instances with proper defaults.

    Attributes:
        id: Unique identifier (UUID), auto-generated if not provided.
        display_name: Human-readable name (required).
        firstname: First name (optional).
        lastname: Last name (optional).
        email: Email address (optional).

    Example::

        # Create from OAuth callback data
        user = AuthenticatedUser.create(
            display_name="Jane Smith",
            id=oauth_user_id,
            firstname="Jane",
            lastname="Smith",
            email="jane@example.com",
        )

        # Check permissions
        if repo.has_permission(user, "/documents", "/read"):
            show_documents()

    See Also:
        RegisteredUser: For users with local accounts and credentials.
    """

    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    id_: str = Field(default_factory=new_id, validation_alias="id", serialization_alias="id")
    display_name_: str = Field(validation_alias="display_name", serialization_alias="display_name")
    firstname_: str | None = Field(default=None, validation_alias="firstname", serialization_alias="firstname")
    lastname_: str | None = Field(default=None, validation_alias="lastname", serialization_alias="lastname")
    email_: str | None = Field(default=None, validation_alias="email", serialization_alias="email")

    @property
    def id(self) -> str:
        return self.id_

    @property
    def display_name(self) -> str:
        return self.display_name_

    @property
    def firstname(self) -> str | None:
        return self.firstname_

    @property
    def lastname(self) -> str | None:
        return self.lastname_

    @property
    def email(self) -> str | None:
        return self.email_

    def name(self, type: UserNameType = "casual") -> str:
        """
        Get a formatted name for the user.

        Args:
            type: The name format to return.

        Returns:
            - ``"technical"``: Returns the user's UUID.
            - ``"casual"``: Returns firstname if available, otherwise display_name.
            - ``"formal"``: Returns "Lastname, Firstname" if both available, otherwise display_name.
            - ``"full"``: Returns "Firstname Lastname" if both available, otherwise display_name.
        """
        if type == "technical":
            return self.id
        elif type == "casual":
            return self.firstname or self.display_name
        elif type == "formal":
            if self.lastname and self.firstname:
                return f"{self.lastname}, {self.firstname}"
            return self.display_name
        else:  # full
            if self.firstname and self.lastname:
                return f"{self.firstname} {self.lastname}"
            return self.display_name

    @staticmethod
    def create(
        display_name: str,
        *,
        id: str | None = None,
        firstname: str | None = None,
        lastname: str | None = None,
        email: str | None = None,
    ) -> "AuthenticatedUser":
        """
        Create an AuthenticatedUser with the given attributes.

        Args:
            display_name: Human-readable display name (required).
            id: Unique identifier. Auto-generated UUID if not provided.
            firstname: First name (optional).
            lastname: Last name (optional).
            email: Email address (optional).

        Returns:
            A new AuthenticatedUser instance.
        """
        return AuthenticatedUser(
            id_=id or new_id(),
            display_name_=display_name,
            firstname_=firstname,
            lastname_=lastname,
            email_=email,
        )


class RolePermission(SQLModel, table=True):
    """
    Junction table linking roles to permissions (many-to-many relationship).

    This is an internal model used by SQLAlchemy to represent the relationship
    between ``Role`` and ``Permission``. You typically don't interact with this
    class directly; instead, use ``Role.permissions`` to access a role's permissions.

    Attributes:
        permission_name: Foreign key to the permission.
        role_name: Foreign key to the role.

    See Also:
        Role: The role that has the permission.
        Permission: The permission granted to the role.
    """

    __tablename__ = "role_permissions"  # type: ignore
    __table_args__ = (PrimaryKeyConstraint("permission_name", "role_name"),)

    permission_name: str = Field(sa_column=Column(String(128), ForeignKey("permissions.name")))
    role_name: str = Field(sa_column=Column(String(64), ForeignKey("roles.name")))


class Permission(SQLModel, table=True):
    """
    A capability that can be granted to users via roles.

    Permissions use a hierarchical path format (e.g., ``"/read"``, ``"/admin/delete"``).
    When checking permissions, a granted permission also covers its sub-paths:
    granting ``"/admin"`` implicitly grants ``"/admin/delete"``, ``"/admin/users"``, etc.

    Permission names are normalized paths (see "Paths" in [`commons.users`][commons.users]): each
    ``"/"``-separated segment holds only lowercase letters, numbers and dashes;
    ``Role.create()`` and the repository normalize the names they are given.

    Attributes:
        name: The permission path (e.g., ``"/read"``, ``"/admin/users"``).
        roles: Roles that have this permission (back-reference).

    Example::

        # Create permissions
        read_perm = Permission(name="/read")
        admin_perm = Permission(name="/admin")

        # Permissions are typically created via Role.create()
        role = Role.create("editor", ["/read", "/write"])

    See Also:
        Role: Groups permissions into named roles.
    """

    __tablename__ = "permissions"  # type: ignore

    name: str = Field(sa_column=Column(String(128), primary_key=True))
    roles: list["Role"] = Relationship(back_populates="permissions", link_model=RolePermission)

    @field_validator("name")
    @classmethod
    def validate_permission_path(cls, v: str) -> str:
        """Normalize the permission name (see ``_normalize_path``)."""
        return _normalize_path("permission", v)


class Role(SQLModel, table=True):
    """
    A named collection of permissions that can be assigned to users.

    Roles group related permissions together for easier management. For example,
    an "editor" role might include ``"/read"`` and ``"/write"`` permissions,
    while an "admin" role might include ``"/admin"`` (covering all admin sub-permissions).

    Roles are assigned to users within a scope via ``RoleAssignment``.

    Attributes:
        name: Unique role name (e.g., ``"admin"``, ``"editor"``, ``"viewer"``).
        permissions: List of permissions granted by this role.
        is_default_role: Whether the role is a default role, defined in code
            (``default_roles`` of the repository) rather than created by the app.
            Default roles are synced into the database when the repository is
            created and can't be changed or deleted at runtime, so apps should
            show them as not editable.

    Example::

        # Create a role with permissions
        admin_role = Role.create("admin", ["/read", "/write", "/admin"])

        # Save to database
        repo.upsert_role(admin_role)

        # Assign to a user within a scope
        repo.add_assignment(user, "/projects/alpha", "admin")

    See Also:
        Permission: Individual capabilities granted by roles.
        RoleAssignment: Links users to roles within scopes.
        Scope: Resource boundaries where roles apply.
    """

    __tablename__ = "roles"  # type: ignore

    name: str = Field(sa_column=Column(String(64), primary_key=True))
    is_default_role: bool = Field(default=False, sa_column=Column(Boolean, nullable=False, default=False))
    permissions: list[Permission] = Relationship(
        back_populates="roles", link_model=RolePermission, sa_relationship_kwargs={"lazy": "selectin"}
    )

    @staticmethod
    def create(name: str, permissions: list[str]) -> "Role":
        """
        Create a Role with the given permissions.

        Args:
            name: Unique role name.
            permissions: List of permission paths (e.g., ``["/read", "/write"]``).

        Returns:
            A new Role instance with Permission objects created for each path.
        """
        normalized = dict.fromkeys(_normalize_path("permission", p) for p in permissions)
        return Role(name=name, permissions=[Permission(name=p) for p in normalized])


class Scope(SQLModel, table=True):
    """
    A resource boundary where role assignments apply.

    Scopes use a hierarchical path format to represent resource boundaries.
    When checking permissions, a role assigned to a parent scope also applies
    to child scopes: a role assigned to ``"/projects"`` also covers
    ``"/projects/alpha"`` and ``"/projects/beta"``.

    Scope names are normalized paths (see "Paths" in [`commons.users`][commons.users]): each
    ``"/"``-separated segment holds only lowercase letters, numbers and dashes, and
    ``"/"`` is the root, which contains every scope. The repository normalizes the
    scopes it is given.

    Attributes:
        name: The scope path (e.g., ``"/projects"``, ``"/projects/alpha"``).

    Example::

        # Scopes are typically created automatically when adding assignments
        repo.add_assignment(user, "/projects/alpha", "editor")

        # Check permission in a scope
        repo.has_permission(user, "/projects/alpha", "/write")

        # Parent scope permissions apply to children
        repo.add_assignment(user, "/projects", "viewer")
        # User can now read /projects/alpha, /projects/beta, etc.

    See Also:
        RoleAssignment: Links users to roles within scopes.
    """

    __tablename__ = "scopes"  # type: ignore

    name: str = Field(sa_column=Column(String(128), primary_key=True))

    @field_validator("name")
    @classmethod
    def validate_permission_path(cls, v: str) -> str:
        """Normalize the scope name (see ``_normalize_path``)."""
        return _normalize_path("scope", v)


class RoleAssignment(SQLModel, table=True):
    """
    Links a registered user to a role within a specific scope.

    Role assignments are the primary mechanism for granting permissions to users.
    Each assignment grants a user all permissions defined in the role, but only
    within the specified scope (and its child scopes).

    Attributes:
        id: Unique identifier for the assignment (UUID).
        scope_name: The scope path where the role applies.
        role_name: The name of the assigned role.
        user_id: The ID of the user receiving the assignment.
        scope: The Scope object (relationship).
        role: The Role object (relationship).
        user: The RegisteredUser object (relationship).

    Example::

        # Assign a role to a user (via repository)
        assignment = repo.add_assignment(user, "/projects/alpha", "editor")

        # The user now has all "editor" permissions within /projects/alpha
        repo.has_permission(user, "/projects/alpha", "/write")  # True
        repo.has_permission(user, "/projects/beta", "/write")  # False (different scope)

        # Remove the assignment
        repo.remove_assignment(assignment)

    See Also:
        Role: Defines what permissions the assignment grants.
        Scope: Defines where the assignment applies.
        RegisteredUser: The user receiving the assignment.
    """

    __tablename__ = "role_assignments"  # type: ignore
    __table_args__ = (UniqueConstraint("user_id", "scope_name", "role_name"),)

    id: str = Field(
        default_factory=new_id,
        sa_column=Column("id", String(64), primary_key=True),
        description="Unique id of the role assignment.",
    )
    scope_name: str = Field(
        sa_column=Column(String(128), ForeignKey("scopes.name")),
        description="The scope on which the role has been assigned.",
    )
    role_name: str = Field(
        sa_column=Column(String(64), ForeignKey("roles.name")),
        description="The role which has been assigned to the user.",
    )
    user_id: str = Field(
        sa_column=Column(String(64), ForeignKey("registered_users.id")),
        description="The user to whom the role has been assigned.",
    )

    scope: Scope = Relationship(sa_relationship_kwargs={"lazy": "selectin"})
    role: Role = Relationship(sa_relationship_kwargs={"lazy": "selectin"})
    user: "RegisteredUser" = Relationship()


class RegisteredUser(SQLModel, table=True):
    """
    A user with a local account stored in the database.

    Registered users have credentials (username and password hash) and can have
    role assignments granting specific permissions. They are authenticated via
    ``UsersRepository.authenticate()`` and can be assigned roles via
    ``UsersRepository.add_assignment()``.

    This class implements the ``User`` protocol and is a SQLModel table class.

    Use ``RegisteredUser.create()`` to construct instances with proper defaults.
    Use ``UsersRepository.hash_password()`` to generate password hashes in code,
    or ``python -m commons.users hash-password`` on the command line (e.g. for
    ``password_hash`` of users configured in the settings).

    Attributes:
        id: Unique identifier (UUID), auto-generated if not provided.
        username: Unique login username.
        password_hash: Bcrypt-hashed password (never store plain passwords), or ``None``
            for a user without a password, who can't sign in with a password
            (e.g. users who sign in with an email link or code only).
        display_name: Human-readable name for display.
        firstname: First name (optional).
        lastname: Last name (optional).
        email: Email address (optional).
        locale: The language the user chose (a language tag such as ``"de"`` or
            ``"de-CH"``), or ``None`` if they never chose one. pyhx uses it to pick
            the language of pages and login mails; it can be changed and saved with
            ``upsert_user``.
        is_active: Whether the user may sign in at all (default ``True``).
        valid_from: Start of the user's access period (UTC), or ``None`` for no start.
        valid_until: End of the access period (UTC, exclusive), or ``None`` for no end.
            An inactive user, or one outside the period, can't sign in and has no
            permissions (see ``can_sign_in``). Existing ``registered_users`` tables are
            not migrated: a database created before commons 1.6 must be recreated.

    Example::

        # Create a new user
        user = RegisteredUser.create(
            username="john.doe",
            password_hash=repo.hash_password("secret123"),
            display_name="John Doe",
            firstname="John",
            lastname="Doe",
            email="john@example.com",
        )
        repo.upsert_user(user)

        # Authenticate
        authenticated = repo.authenticate("john.doe", "secret123")

        # Assign roles
        repo.add_assignment(user, "/projects/alpha", "admin")

        # Check permissions
        if repo.has_permission(user, "/projects/alpha", "/admin/delete"):
            delete_project()

    See Also:
        AnonymousUser: For unauthenticated visitors.
        AuthenticatedUser: For externally authenticated users without local accounts.
        RoleAssignment: For granting permissions to registered users.
    """

    __tablename__ = "registered_users"  # type: ignore

    id_: str = Field(
        default_factory=new_id,
        validation_alias="id",
        serialization_alias="id",
        sa_column=Column("id", String(64), primary_key=True),
        description="Unique id of the user.",
    )

    username_: str = Field(
        validation_alias="username",
        serialization_alias="username",
        sa_column=Column("username", String(64), unique=True),
    )
    password_hash_: str | None = Field(
        default=None,
        validation_alias="password_hash",
        serialization_alias="password_hash",
        sa_column=Column("password_hash", String(256)),
    )
    display_name_: str = Field(
        validation_alias="display_name",
        serialization_alias="display_name",
        sa_column=Column("display_name", Unicode(128)),
    )
    firstname_: str | None = Field(
        default=None,
        validation_alias="firstname",
        serialization_alias="firstname",
        sa_column=Column("firstname", Unicode(64)),
    )
    lastname_: str | None = Field(
        default=None,
        validation_alias="lastname",
        serialization_alias="lastname",
        sa_column=Column("lastname", Unicode(64)),
    )
    email_: str | None = Field(
        default=None, validation_alias="email", serialization_alias="email", sa_column=Column("email", String(128))
    )
    locale_: str | None = Field(
        default=None, validation_alias="locale", serialization_alias="locale", sa_column=Column("locale", String(35))
    )
    is_active_: bool = Field(
        default=True,
        validation_alias="is_active",
        serialization_alias="is_active",
        sa_column=Column("is_active", Boolean, nullable=False, default=True),
    )
    valid_from_: datetime | None = Field(
        default=None,
        validation_alias="valid_from",
        serialization_alias="valid_from",
        sa_column=Column("valid_from", DateTime),
    )
    valid_until_: datetime | None = Field(
        default=None,
        validation_alias="valid_until",
        serialization_alias="valid_until",
        sa_column=Column("valid_until", DateTime),
    )

    @property
    def id(self) -> str:
        return self.id_

    @property
    def username(self) -> str:
        return self.username_

    @property
    def password_hash(self) -> str | None:
        return self.password_hash_

    @property
    def display_name(self) -> str:
        return self.display_name_

    @property
    def firstname(self) -> str | None:
        return self.firstname_

    @property
    def lastname(self) -> str | None:
        return self.lastname_

    @property
    def email(self) -> str | None:
        return self.email_

    @property
    def locale(self) -> str | None:
        return self.locale_

    @locale.setter
    def locale(self, value: str | None) -> None:
        self.locale_ = value

    @property
    def is_active(self) -> bool:
        return self.is_active_

    @is_active.setter
    def is_active(self, value: bool) -> None:
        self.is_active_ = value

    @property
    def valid_from(self) -> datetime | None:
        return _as_utc(self.valid_from_)

    @valid_from.setter
    def valid_from(self, value: datetime | None) -> None:
        self.valid_from_ = _as_naive_utc(value)

    @property
    def valid_until(self) -> datetime | None:
        return _as_utc(self.valid_until_)

    @valid_until.setter
    def valid_until(self, value: datetime | None) -> None:
        self.valid_until_ = _as_naive_utc(value)

    def can_sign_in(self, at: datetime | None = None) -> bool:
        """
        Whether the user may sign in and use their permissions at ``at``.

        True if the user is active and ``at`` lies within the access period:
        not before ``valid_from`` and before ``valid_until`` (exclusive); a
        missing bound doesn't limit. Otherwise the user can't sign in
        (``UsersRepository.authenticate``, login links and codes) and has no
        permissions (``UsersRepository.has_permission``).

        Args:
            at: The time to check, timezone-aware; defaults to now (UTC). A naive
                value is taken as UTC.
        """
        at = _as_utc(at) or datetime.now(timezone.utc)
        valid_from = self.valid_from
        valid_until = self.valid_until
        return self.is_active and (valid_from is None or valid_from <= at) and (valid_until is None or at < valid_until)

    def name(self, type: UserNameType = "casual") -> str:
        """
        Get a formatted name for the user.

        Args:
            type: The name format to return.

        Returns:
            - ``"technical"``: Returns the username.
            - ``"casual"``: Returns firstname if available, otherwise display_name.
            - ``"formal"``: Returns "Lastname, Firstname" if both available, otherwise display_name.
            - ``"full"``: Returns "Firstname Lastname" if both available, otherwise display_name.
        """
        if type == "technical":
            return self.username
        elif type == "casual":
            return self.firstname or self.display_name
        elif type == "formal":
            if self.lastname and self.firstname:
                return f"{self.lastname}, {self.firstname}"
            return self.display_name
        else:  # full
            if self.firstname and self.lastname:
                return f"{self.firstname} {self.lastname}"
            return self.display_name

    @staticmethod
    def create(
        username: str,
        password_hash: str | None,
        display_name: str,
        *,
        id: str | None = None,
        firstname: str | None = None,
        lastname: str | None = None,
        email: str | None = None,
        locale: str | None = None,
        is_active: bool = True,
        valid_from: datetime | None = None,
        valid_until: datetime | None = None,
    ) -> "RegisteredUser":
        """
        Create a RegisteredUser with the given attributes.

        Args:
            username: Unique login username (required).
            password_hash: Pre-hashed password, or ``None`` for a user without a password.
                Use ``UsersRepository.hash_password()``
                to generate this value.
            display_name: Human-readable display name (required).
            id: Unique identifier. Auto-generated UUID if not provided.
            firstname: First name (optional).
            lastname: Last name (optional).
            email: Email address (optional).
            locale: The language the user chose, e.g. ``"de"`` (optional).
            is_active: Whether the user may sign in at all (default ``True``).
            valid_from: Start of the access period, timezone-aware (optional, no limit if ``None``).
            valid_until: End of the access period, exclusive, timezone-aware (optional, no limit if ``None``).

        Returns:
            A new RegisteredUser instance.

        Example::

            user = RegisteredUser.create(
                username="jane.doe",
                password_hash=repo.hash_password("password123"),
                display_name="Jane Doe",
                firstname="Jane",
                lastname="Doe",
            )
        """
        return RegisteredUser(
            id_=id or new_id(),
            username_=username,
            password_hash_=password_hash,
            display_name_=display_name,
            firstname_=firstname,
            lastname_=lastname,
            email_=email,
            locale_=locale,
            is_active_=is_active,
            valid_from_=_as_naive_utc(valid_from),
            valid_until_=_as_naive_utc(valid_until),
        )


def _as_utc(value: datetime | None) -> datetime | None:
    """``value`` in UTC, timezone-aware; a naive value (as read from the database) is taken as UTC."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _as_naive_utc(value: datetime | None) -> datetime | None:
    """``value`` as naive UTC, as stored in the database (``DateTime`` keeps no time zone on every engine)."""
    utc = _as_utc(value)
    return utc.replace(tzinfo=None) if utc is not None else None
