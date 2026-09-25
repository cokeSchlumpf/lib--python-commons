import pytest

from commons.string_operators import (
    approx_similarity,
    ensure_path_slugified,
    normalize_path,
    normalize_slug,
    pluralize,
    remove_symbols,
    to_camel_case,
    to_kebabcase,
    to_pascal_case,
    to_snake_case,
    to_title_case,
)


class TestApproxSimilarity:
    def test_exact_match(self):
        assert approx_similarity("hello world", "hello world") is True

    def test_no_match(self):
        assert approx_similarity("hello world", "goodbye moon") is False

    def test_partial_match_above_threshold(self):
        assert approx_similarity("the quick brown fox", "quick brown", min_similarity=0.6) is True

    def test_partial_match_below_threshold(self):
        assert approx_similarity("hello world", "hxllo wxrld", min_similarity=0.9) is False

    def test_empty_s2(self):
        assert approx_similarity("hello world", "") is False

    def test_s1_shorter_than_s2(self):
        assert approx_similarity("hi", "hello world") is False

    def test_case_insensitive(self):
        assert approx_similarity("Hello World", "hello world") is True

    def test_whitespace_normalization(self):
        assert approx_similarity("hello   world", "hello world") is True


class TestEnsurePathSlugified:
    def test_empty_string(self):
        assert ensure_path_slugified("") == "/"

    def test_root_path(self):
        assert ensure_path_slugified("/") == "/"

    def test_single_segment(self):
        assert ensure_path_slugified("/Hello World") == "/hello-world"

    def test_multiple_segments(self):
        assert ensure_path_slugified("/Hello World/My-File") == "/hello-world/my-file"

    def test_preserves_structure(self):
        assert ensure_path_slugified("/Foo/Bar/Baz") == "/foo/bar/baz"

    def test_handles_special_chars(self):
        assert ensure_path_slugified("/Café/Naïve") == "/cafe/naive"

    def test_preserves_file_extension(self):
        assert ensure_path_slugified("/Hello World/My File.pdf") == "/hello-world/my-file.pdf"

    def test_preserves_extension_without_spaces(self):
        assert ensure_path_slugified("/Hello World/My File") == "/hello-world/my-file"

    def test_lowercases_extension(self):
        assert ensure_path_slugified("/Hello.World/File.PDF") == "/hello-world/file.pdf"

    def test_preserves_docx_extension(self):
        assert ensure_path_slugified("/Reports/Annual Report 2024.docx") == "/reports/annual-report-2024.docx"

    def test_dots_in_directory_names_slugified(self):
        assert ensure_path_slugified("/v1.0/file.txt") == "/v1-0/file.txt"

    def test_preserves_multiple_dots_in_filename(self):
        assert ensure_path_slugified("/docs/My Report.2024.pdf") == "/docs/my-report.2024.pdf"

    def test_preserves_compound_extension(self):
        assert ensure_path_slugified("/archives/backup.tar.gz") == "/archives/backup.tar.gz"


class TestNormalizePath:
    def test_empty_string(self):
        assert normalize_path("") == "/"

    def test_multiple_slashes(self):
        assert normalize_path("///foo///bar///") == "/foo/bar"

    def test_no_leading_slash(self):
        assert normalize_path("foo/bar") == "/foo/bar"

    def test_trailing_slash_removed(self):
        assert normalize_path("/foo/bar/") == "/foo/bar"

    def test_root_preserved(self):
        assert normalize_path("/") == "/"

    def test_normal_path_unchanged(self):
        assert normalize_path("/foo/bar") == "/foo/bar"


class TestNormalizeSlug:
    def test_lowercase(self):
        assert normalize_slug("HELLO") == "hello"

    def test_removes_accents(self):
        assert normalize_slug("café") == "cafe"

    def test_replaces_spaces_with_hyphens(self):
        assert normalize_slug("hello world") == "hello-world"

    def test_removes_consecutive_hyphens(self):
        assert normalize_slug("hello---world") == "hello-world"

    def test_strips_leading_trailing_hyphens(self):
        assert normalize_slug("--hello--") == "hello"

    def test_mixed_input(self):
        assert normalize_slug("  Hello  World!  ") == "hello-world"


class TestPluralize:
    def test_word_ending_in_y(self):
        assert pluralize("category") == "categories"

    def test_word_ending_in_s(self):
        assert pluralize("bus") == "buses"

    def test_word_ending_in_sh(self):
        assert pluralize("brush") == "brushes"

    def test_word_ending_in_ch(self):
        assert pluralize("watch") == "watches"

    def test_word_ending_in_x(self):
        assert pluralize("box") == "boxes"

    def test_regular_word(self):
        assert pluralize("cat") == "cats"


class TestRemoveSymbols:
    def test_removes_all_symbols(self):
        assert remove_symbols("hello!@#$%world") == "helloworld"

    def test_preserves_alphanumeric(self):
        assert remove_symbols("hello123") == "hello123"

    def test_preserves_whitespace(self):
        assert remove_symbols("hello world!") == "hello world"

    def test_with_allowed_chars(self):
        assert remove_symbols("hello-world_test!", allowed="-_") == "hello-world_test"

    def test_empty_string(self):
        assert remove_symbols("") == ""


class TestToCamelCase:
    def test_snake_case(self):
        assert to_camel_case("document_title") == "documentTitle"

    def test_kebab_case(self):
        assert to_camel_case("document-title") == "documentTitle"

    def test_space_separated(self):
        assert to_camel_case("document title") == "documentTitle"

    def test_pascal_case(self):
        assert to_camel_case("DocumentTitle") == "documenttitle"

    def test_empty_string(self):
        assert to_camel_case("") == ""

    def test_single_word(self):
        assert to_camel_case("hello") == "hello"


class TestToKebabcase:
    def test_camel_case(self):
        assert to_kebabcase("documentTitle") == "document-title"

    def test_pascal_case(self):
        assert to_kebabcase("DocumentTitle") == "document-title"

    def test_snake_case(self):
        assert to_kebabcase("document_title") == "document-title"

    def test_space_separated(self):
        assert to_kebabcase("Document Title") == "document-title"

    def test_mixed(self):
        assert to_kebabcase("Document_Title 123") == "document-title-123"

    def test_empty_string(self):
        assert to_kebabcase("") == ""


class TestToPascalCase:
    def test_snake_case(self):
        assert to_pascal_case("document_title") == "DocumentTitle"

    def test_kebab_case(self):
        assert to_pascal_case("document-title") == "DocumentTitle"

    def test_space_separated(self):
        assert to_pascal_case("document title") == "DocumentTitle"

    def test_camel_case(self):
        assert to_pascal_case("documentTitle") == "DocumentTitle"

    def test_empty_string(self):
        assert to_pascal_case("") == ""


class TestToSnakeCase:
    def test_camel_case(self):
        assert to_snake_case("documentTitle") == "document_title"

    def test_pascal_case(self):
        assert to_snake_case("DocumentTitle") == "document_title"

    def test_kebab_case(self):
        assert to_snake_case("document-title") == "document_title"

    def test_space_separated(self):
        assert to_snake_case("Document Title") == "document_title"

    def test_empty_string(self):
        assert to_snake_case("") == ""


class TestToTitleCase:
    def test_camel_case(self):
        assert to_title_case("documentTitle") == "Document Title"

    def test_kebab_case(self):
        assert to_title_case("document-title") == "Document Title"

    def test_snake_case(self):
        assert to_title_case("document_title") == "Document Title"

    def test_pascal_case(self):
        assert to_title_case("DocumentTitle") == "Document Title"

    def test_empty_string(self):
        assert to_title_case("") == ""

    def test_single_word(self):
        assert to_title_case("hello") == "Hello"
