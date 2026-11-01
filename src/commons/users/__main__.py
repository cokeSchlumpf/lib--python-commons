"""
Command line helpers for user management.

Usage::

    # Prompt for a password (input hidden, asked twice) and print its bcrypt hash
    python -m commons.users hash-password

    # Read the password from stdin, e.g. in scripts
    echo -n "secret" | python -m commons.users hash-password --stdin

The printed hash can be used as ``password_hash`` of a user in the settings
(see [`StandardUser`][commons.settings.StandardUser]).
"""

import argparse
import getpass
import sys

from commons.users.repository import _default_hash_password


def _read_password(from_stdin: bool) -> str:
    if from_stdin:
        return sys.stdin.read().rstrip("\r\n")

    password = getpass.getpass("Password: ")
    if password != getpass.getpass("Repeat password: "):
        raise SystemExit("Passwords do not match.")
    return password


def _hash_password(args: argparse.Namespace) -> None:
    password = _read_password(args.stdin)
    if not password:
        raise SystemExit("Password must not be empty.")
    print(_default_hash_password(password))


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m commons.users", description="User management helpers.")
    commands = parser.add_subparsers(dest="command", required=True)

    hash_password = commands.add_parser(
        "hash-password", help="Print a bcrypt hash for use as `password_hash` in the user settings."
    )
    hash_password.add_argument(
        "--stdin", action="store_true", help="Read the password from stdin instead of prompting."
    )
    hash_password.set_defaults(func=_hash_password)

    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
