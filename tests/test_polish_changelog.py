from pathlib import Path

import pytest

from scripts import polish_changelog
from scripts.polish_changelog import HIGHLIGHTS_HEADING, main, polish, split_body, validate

NOTES = """\
## [1.1.0](https://github.com/owner/repo/compare/v1.0.0...v1.1.0) (2026-09-26)


### Features

* add tree rendering ([#12](https://github.com/owner/repo/issues/12)) ([abc1234](https://github.com/owner/repo/commit/abc1234def))


### Bug Fixes

* handle empty paths ([#13](https://github.com/owner/repo/issues/13)) ([def5678](https://github.com/owner/repo/commit/def5678abc))"""

POLISHED = f"""\
## [1.1.0](https://github.com/owner/repo/compare/v1.0.0...v1.1.0) (2026-09-26)

{HIGHLIGHTS_HEADING}

Trees can now be rendered, and empty paths no longer fail.

### Features

* Render trees as text ([#12](https://github.com/owner/repo/issues/12)) ([abc1234](https://github.com/owner/repo/commit/abc1234def))

### Bug Fixes

* Empty paths are handled correctly ([#13](https://github.com/owner/repo/issues/13)) ([def5678](https://github.com/owner/repo/commit/def5678abc))"""

BODY = f""":robot: I have created a release *beep* *boop*
---


{NOTES}

---
This PR was generated with [Release Please](https://github.com/googleapis/release-please)."""

CHANGELOG = f"# Changelog\n\n{NOTES}\n\n## 1.0.0 (2026-09-01)\n\n* initial release\n"


def fake_llm(answer: str):
    def complete(instructions: str, prompt: str) -> str:
        assert NOTES in prompt
        return answer

    return complete


def failing_llm(instructions: str, prompt: str) -> str:
    raise RuntimeError("API not reachable")


class TestSplitBody:
    def test_splits_header_notes_and_footer(self) -> None:
        header, notes, footer = split_body(BODY)  # type: ignore[misc]
        assert header == ":robot: I have created a release *beep* *boop*"
        assert notes == NOTES
        assert footer.startswith("This PR was generated")

    def test_returns_none_without_delimiter(self) -> None:
        assert split_body("no notes here") is None


class TestValidate:
    def test_accepts_valid_polished_notes(self) -> None:
        assert validate(NOTES, POLISHED) == []

    def test_rejects_changed_version_heading(self) -> None:
        assert validate(NOTES, POLISHED.replace("## [1.1.0]", "## [2.0.0]", 1))

    def test_rejects_missing_highlights(self) -> None:
        assert validate(NOTES, POLISHED.replace(HIGHLIGHTS_HEADING, "### Summary"))

    def test_rejects_missing_link(self) -> None:
        assert validate(NOTES, POLISHED.replace("([#13](https://github.com/owner/repo/issues/13)) ", ""))

    def test_rejects_changed_sections(self) -> None:
        assert validate(NOTES, POLISHED.replace("### Bug Fixes", "### Fixes"))

    def test_rejects_notes_delimiter(self) -> None:
        assert validate(NOTES, POLISHED + "\n---\n")

    def test_rejects_too_long_output(self) -> None:
        assert validate(NOTES, POLISHED + "x" * 10_000)


class TestPolish:
    def test_returns_polished_notes(self) -> None:
        assert polish(NOTES, "", fake_llm(POLISHED)) == POLISHED

    def test_keeps_original_on_api_error(self) -> None:
        assert polish(NOTES, "", failing_llm) == NOTES

    def test_keeps_original_on_invalid_output(self) -> None:
        assert polish(NOTES, "", fake_llm("Something completely different")) == NOTES

    def test_skips_already_polished_notes(self) -> None:
        assert polish(POLISHED, "", failing_llm) == POLISHED


class TestMain:
    @pytest.fixture(autouse=True)
    def no_github(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(polish_changelog, "fetch_pull_request_context", lambda notes: "")

    def write_files(self, tmp_path: Path, body: str = BODY, changelog: str = CHANGELOG) -> tuple[Path, Path]:
        body_file = tmp_path / "body.md"
        changelog_file = tmp_path / "CHANGELOG.md"
        body_file.write_text(body)
        changelog_file.write_text(changelog)
        return body_file, changelog_file

    def run(self, body_file: Path, changelog_file: Path, complete) -> int:
        return main(["--body", str(body_file), "--changelog", str(changelog_file)], complete)

    def test_updates_body_and_changelog(self, tmp_path: Path) -> None:
        body_file, changelog_file = self.write_files(tmp_path)

        assert self.run(body_file, changelog_file, fake_llm(POLISHED)) == 0

        assert split_body(body_file.read_text())[1] == POLISHED  # type: ignore[index]
        changelog = changelog_file.read_text()
        assert changelog.startswith(f"# Changelog\n\n{POLISHED}")
        assert "## 1.0.0 (2026-09-01)" in changelog

    def test_leaves_files_unchanged_on_api_error(self, tmp_path: Path) -> None:
        body_file, changelog_file = self.write_files(tmp_path)

        assert self.run(body_file, changelog_file, failing_llm) == 0

        assert body_file.read_text() == BODY
        assert changelog_file.read_text() == CHANGELOG

    def test_leaves_files_unchanged_if_notes_not_in_changelog(self, tmp_path: Path) -> None:
        body_file, changelog_file = self.write_files(tmp_path, changelog="# Changelog\n")

        assert self.run(body_file, changelog_file, fake_llm(POLISHED)) == 0

        assert body_file.read_text() == BODY
        assert changelog_file.read_text() == "# Changelog\n"
