import abc
from pathlib import PurePosixPath
from typing import Callable

import bcrypt  # type: ignore
from pydantic import BaseModel

from commons.settings import StandardUserSettings
from commons.users.user import (
    AnonymousUser,
    AuthenticatedUser,
    RegisteredUser,
    Role,
    RoleAssignment,
    User,
)


PasswordHasher = Callable[[str], str]
"""A callable that takes a plain-text password and returns a hashed password."""

PasswordVerifier = Callable[[str, str], bool]
"""A callable that takes (plain_password, hashed_password) and returns True if they match."""


def _default_hash_password(password: str) -> str:
    """Hash a password using bcrypt with auto-generated salt."""
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def _default_verify_password(password: str, hashed: str) -> bool:
    """Verify a password against a bcrypt hash."""
    return bcrypt.checkpw(password.encode(), hashed.encode())


class DefaultRoleAssignment(BaseModel):
    """A default role assignment applied to users based on their authentication state."""

    scope: str
    """The scope path (e.g., '/projects/my-project') where the role applies."""

    role: str
    """The role name to assign."""


class UsersRepository(abc.ABC):
    """
    Abstract base class for user repository implementations.

    Provides user management, authentication, and permission checking functionality.
    Subclasses must implement the abstract methods to provide database-specific operations.

    Args:
        default_roles: Predefined roles available without database lookup.
        anonymous_default_permissions: Role assignments applied to anonymous (unauthenticated) users.
        authenticated_default_permissions: Role assignments applied to authenticated but unregistered users.
        registered_default_permissions: Role assignments applied to all registered users.
        password_hasher: Custom password hashing function. Defaults to bcrypt.
        password_verifier: Custom password verification function. Defaults to bcrypt.
    """

    def __init__(
        self,
        default_roles: list[Role] | None,
        anonymous_default_permissions: list[DefaultRoleAssignment] | None,
        authenticated_default_permissions: list[DefaultRoleAssignment] | None,
        registered_default_permissions: list[DefaultRoleAssignment] | None,
        password_hasher: PasswordHasher | None = None,
        password_verifier: PasswordVerifier | None = None,
    ):
        self.default_roles = default_roles or []
        self.anonymous_default_permissions = anonymous_default_permissions or []
        self.authenticated_default_permissions = authenticated_default_permissions or []
        self.registered_default_permissions = registered_default_permissions or []
        self._password_hasher = password_hasher or _default_hash_password
        self._password_verifier = password_verifier or _default_verify_password

    # Public methods (alphabetically)

    @abc.abstractmethod
    def add_assignment(self, user: RegisteredUser | str, scope: str, role: str) -> RoleAssignment:
        """
        Add a role assignment to a user.

        Args:
            user: The user instance or username to assign the role to.
            scope: The scope path (e.g., '/projects/my-project') where the role applies.
            role: The role name to assign.

        Returns:
            The created RoleAssignment.
        """
        ...

    def authenticate(self, username: str, password: str) -> RegisteredUser | None:
        """
        Verify credentials and return the user if valid.

        Args:
            username: The username to authenticate.
            password: The plain-text password to verify.

        Returns:
            The authenticated RegisteredUser if credentials are valid, None otherwise.
        """
        user = self.find_user_by_username(username)
        if not user:
            return None
        if self._password_verifier(password, user.password_hash):
            return user
        return None

    def check_permission(self, user: User, scope: str, permission: str) -> None:
        """
        Check if a user has a permission, raising an error if not.

        Args:
            user: The user to check permissions for.
            scope: The scope path to check the permission in.
            permission: The permission path to check.

        Raises:
            LookupError: If the user does not have the required permission.
        """
        if not self.has_permission(user, scope, permission):
            raise LookupError(
                f"User `{user.display_name}` does not have the permission `{permission}` in scope `{scope}`."
            )

    @abc.abstractmethod
    def delete_role(self, role: Role | str) -> None:
        """
        Delete a role.

        Args:
            role: The role instance or role name to delete.
        """
        ...

    @abc.abstractmethod
    def delete_user(self, user: RegisteredUser | str) -> None:
        """
        Delete a user.

        Args:
            user: The user instance or username to delete.
        """
        ...

    def find_role_by_name(self, name: str) -> Role | None:
        """
        Find a role by its name.

        Searches both default_roles and the database.

        Args:
            name: The role name to search for.

        Returns:
            The Role if found, None otherwise.
        """
        for role in self.default_roles:
            if role.name == name:
                return role

        return self._find_role_by_name(name)

    @abc.abstractmethod
    def find_user_by_id(self, user_id: str) -> RegisteredUser | None:
        """
        Find a user by their unique ID.

        Args:
            user_id: The user's unique identifier (UUID).

        Returns:
            The RegisteredUser if found, None otherwise.
        """
        ...

    @abc.abstractmethod
    def find_user_by_username(self, username: str) -> RegisteredUser | None:
        """
        Find a user by their username.

        Args:
            username: The user's unique username.

        Returns:
            The RegisteredUser if found, None otherwise.
        """
        ...

    def get_role_by_name(self, name: str) -> Role:
        """
        Get a role by its name, raising an error if not found.

        Args:
            name: The role name to search for.

        Returns:
            The Role.

        Raises:
            KeyError: If no role exists with the given name.
        """
        role = self.find_role_by_name(name)

        if role:
            return role

        raise KeyError(f"No role found with name `{name}`.")

    @abc.abstractmethod
    def get_role_assignments(self, user: RegisteredUser | str) -> list[RoleAssignment]:
        """
        Fetch the role assignments assigned to a user.

        Args:
            user: The user instance or username to get assignments for.

        Returns:
            List of RoleAssignments for the user.
        """
        ...

    def get_user_by_id(self, user_id: str) -> RegisteredUser:
        """
        Get a user by their unique ID, raising an error if not found.

        Args:
            user_id: The user's unique identifier (UUID).

        Returns:
            The RegisteredUser.

        Raises:
            KeyError: If no user exists with the given ID.
        """
        user = self.find_user_by_id(user_id)
        if not user:
            raise KeyError(f"No user found with id `{user_id}`.")
        return user

    def get_user_by_username(self, username: str) -> RegisteredUser:
        """
        Get a user by their username, raising an error if not found.

        Args:
            username: The user's unique username.

        Returns:
            The RegisteredUser.

        Raises:
            KeyError: If no user exists with the given username.
        """
        user = self.find_user_by_username(username)
        if not user:
            raise KeyError(f"No user found with username `{username}`.")
        return user

    def has_permission(self, user: User, scope: str, permission: str) -> bool:
        """
        Check whether a user has a specific permission in a scope.

        Permission checking is based on the user type:
        - AnonymousUser: Checks anonymous_default_permissions
        - AuthenticatedUser: Checks authenticated_default_permissions
        - RegisteredUser: Checks registered_default_permissions and user-specific assignments

        Args:
            user: The user to check permissions for.
            scope: The scope path to check the permission in (e.g., '/projects/my-project').
            permission: The permission path to check (e.g., '/read', '/admin/delete').

        Returns:
            True if the user has the permission, False otherwise.
        """
        if isinstance(user, AnonymousUser):
            return any(
                self.role_has_permission(p.scope, p.role, scope, permission) for p in self.anonymous_default_permissions
            )
        elif isinstance(user, AuthenticatedUser):
            return any(
                self.role_has_permission(p.scope, p.role, scope, permission)
                for p in self.authenticated_default_permissions
            )
        elif isinstance(user, RegisteredUser):
            return self.registered_user_has_permission(user, scope, permission)
        else:
            return False

    def hash_password(self, password: str) -> str:
        """
        Hash a plain-text password using the configured hasher.

        Args:
            password: The plain-text password to hash.

        Returns:
            The hashed password string.
        """
        return self._password_hasher(password)

    def init_from_settings(self, settings: StandardUserSettings) -> None:
        """
        Initialize users from settings configuration.

        Creates or updates users defined in the settings, hashing their passwords
        and assigning their configured roles.

        Args:
            settings: The user settings containing user definitions.
        """
        for user_config in settings.users:
            existing_user = self.find_user_by_username(user_config.username)

            user = RegisteredUser.create(
                id=existing_user.id if existing_user else None,
                username=user_config.username,
                password_hash=self.hash_password(user_config.password),
                display_name=f"{user_config.firstname} {user_config.lastname}",
                firstname=user_config.firstname,
                lastname=user_config.lastname,
                email=user_config.email,
            )
            self.upsert_user(user)

            for role_config in user_config.roles:
                self.add_assignment(user, role_config.scope, role_config.role)

    @abc.abstractmethod
    def list_roles(self) -> list[Role]:
        """
        List all roles from the database.

        Note: This does not include default_roles. Use default_roles attribute
        to access predefined roles.

        Returns:
            List of all Role objects in the database.
        """
        ...

    def registered_user_has_permission(self, user: RegisteredUser, scope: str, permission: str) -> bool:
        """
        Check whether a registered user has a specific permission in a scope.

        Checks both registered_default_permissions (applied to all registered users)
        and the user's individual role assignments.

        Args:
            user: The registered user to check permissions for.
            scope: The scope path to check the permission in.
            permission: The permission path to check.

        Returns:
            True if the user has the permission, False otherwise.
        """
        for default_permission in self.registered_default_permissions:
            role = self.get_role_by_name(default_permission.role)
            has_permission = self.role_has_permission(default_permission.scope, role, scope, permission)
            if has_permission:
                return True

        return any(
            self.role_has_permission(ra.scope.name, ra.role or self.get_role_by_name(ra.role_name), scope, permission)
            for ra in self.get_role_assignments(user)
        )

    @abc.abstractmethod
    def remove_assignment(self, assignment: RoleAssignment | str) -> None:
        """
        Remove a role assignment.

        Args:
            assignment: The RoleAssignment instance or assignment ID (UUID) to remove.
        """
        ...

    def role_has_permission(self, scope: str, role: Role | str, scope_to_check: str, permission_to_check: str) -> bool:
        """
        Check whether a role grants a specific permission within a scope.

        Uses path-based matching: a role with permission '/admin' also grants '/admin/delete',
        and a role assigned to scope '/projects' also applies to '/projects/my-project'.

        Args:
            scope: The scope path where the role is assigned.
            role: The role instance or role name to check.
            scope_to_check: The scope path to verify access for.
            permission_to_check: The permission path to verify.

        Returns:
            True if the role grants the permission in the scope, False otherwise.
        """
        if not self._scope_contains_scope(scope, scope_to_check):
            return False

        if isinstance(role, str):
            role = self.get_role_by_name(role)

        return any(self._permission_contains_permission(p.name, permission_to_check) for p in role.permissions)

    def update_password(self, user: RegisteredUser | str, new_password: str) -> RegisteredUser:
        """
        Update a user's password.

        Args:
            user: The user instance or username whose password should be updated.
            new_password: The new plain-text password (will be hashed before storage).

        Returns:
            The updated RegisteredUser with the new password hash.

        Raises:
            KeyError: If a username is provided and no user exists with that username.
        """
        if isinstance(user, str):
            user = self.get_user_by_username(user)
        new_hash = self.hash_password(new_password)
        updated_user = RegisteredUser.create(
            username=user.username,
            password_hash=new_hash,
            display_name=user.display_name,
            id=user.id,
            firstname=user.firstname,
            lastname=user.lastname,
            email=user.email,
        )
        return self.upsert_user(updated_user)

    @abc.abstractmethod
    def upsert_role(self, role: Role) -> Role:
        """
        Create or update a role.

        If a role with the same name exists, it is updated. Otherwise, a new role is created.

        Args:
            role: The role to create or update.

        Returns:
            The created or updated Role.
        """
        ...

    @abc.abstractmethod
    def upsert_user(self, user: RegisteredUser) -> RegisteredUser:
        """
        Create or update a user.

        If a user with the same ID exists, it is updated. Otherwise, a new user is created.

        Args:
            user: The user to create or update.

        Returns:
            The created or updated RegisteredUser.
        """
        ...

    # Private methods (alphabetically)

    @abc.abstractmethod
    def _find_role_by_name(self, name: str) -> Role | None:
        """
        Search for a role in the database by name.

        Args:
            name: The role name to search for.

        Returns:
            The Role if found, None otherwise.
        """
        ...

    def _permission_contains_permission(self, allowed_permission: str, permission_to_check: str) -> bool:
        """
        Check whether permission_to_check is within allowed_permission.

        Uses path-based containment: '/admin' contains '/admin/delete'.

        Args:
            allowed_permission: The permission path that is granted.
            permission_to_check: The permission path to verify.

        Returns:
            True if permission_to_check is equal to or a sub-path of allowed_permission.
        """
        return PurePosixPath(permission_to_check).is_relative_to(PurePosixPath(allowed_permission))

    def _scope_contains_scope(self, allowed_scope: str, scope_to_check: str) -> bool:
        """
        Check whether scope_to_check is within allowed_scope.

        Uses path-based containment: '/projects' contains '/projects/my-project'.

        Args:
            allowed_scope: The scope path that is granted.
            scope_to_check: The scope path to verify.

        Returns:
            True if scope_to_check is equal to or a sub-path of allowed_scope.
        """
        return PurePosixPath(scope_to_check).is_relative_to(PurePosixPath(allowed_scope))
