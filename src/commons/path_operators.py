import subprocess

from pathlib import Path
from typing import Optional


def get_project_root_dir() -> Path:
    """
    Returns the root dir of the current project.

    This root dir is usually used to search for settings, local data, etc..

    If the current project is a Git repository, the root of the Git repository will be returned. Otherwise the current working directory will be returned.
    """

    return get_git_root_dir() or Path.cwd()


def get_git_root_dir() -> Optional[Path]:
    """Return the root directory of the git project."""

    try:
        result = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=True)
        return Path(result.stdout.strip())
    except (subprocess.CalledProcessError, FileNotFoundError):
        # CalledProcessError → not a git repo
        # FileNotFoundError → git not installed
        return None
