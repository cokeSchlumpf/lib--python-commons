import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock

from commons.path_operators import get_git_root_dir, get_project_root_dir


class TestGetGitRootDir:
    def test_returns_path_when_in_git_repo(self):
        mock_result = MagicMock()
        mock_result.stdout = "/path/to/repo\n"

        with patch("commons.path_operators.subprocess.run", return_value=mock_result) as mock_run:
            result = get_git_root_dir()

            mock_run.assert_called_once_with(
                ["git", "rev-parse", "--show-toplevel"],
                capture_output=True,
                text=True,
                check=True,
            )
            assert result == Path("/path/to/repo")

    def test_returns_none_when_not_git_repo(self):
        with patch(
            "commons.path_operators.subprocess.run",
            side_effect=subprocess.CalledProcessError(128, "git"),
        ):
            result = get_git_root_dir()
            assert result is None

    def test_returns_none_when_git_not_installed(self):
        with patch(
            "commons.path_operators.subprocess.run",
            side_effect=FileNotFoundError("git not found"),
        ):
            result = get_git_root_dir()
            assert result is None


class TestGetProjectRootDir:
    def test_returns_git_root_when_available(self):
        mock_result = MagicMock()
        mock_result.stdout = "/path/to/repo\n"

        with patch("commons.path_operators.subprocess.run", return_value=mock_result):
            result = get_project_root_dir()
            assert result == Path("/path/to/repo")

    def test_returns_cwd_when_not_git_repo(self):
        with patch(
            "commons.path_operators.subprocess.run",
            side_effect=subprocess.CalledProcessError(128, "git"),
        ):
            with patch("commons.path_operators.Path.cwd", return_value=Path("/current/dir")):
                result = get_project_root_dir()
                assert result == Path("/current/dir")
