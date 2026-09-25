import pytest

from commons.url_operators import remove_query_param, set_query_param


class TestSetQueryParam:
    def test_add_param_to_url_without_query_string(self) -> None:
        result = set_query_param("https://example.com/path", "foo", "bar")
        assert result == "https://example.com/path?foo=bar"

    def test_add_param_to_url_with_existing_params(self) -> None:
        result = set_query_param("https://example.com/path?existing=value", "foo", "bar")
        assert "foo=bar" in result
        assert "existing=value" in result

    def test_update_existing_param_value(self) -> None:
        result = set_query_param("https://example.com/path?foo=old", "foo", "new")
        assert "foo=new" in result
        assert "foo=old" not in result

    def test_works_with_relative_urls(self) -> None:
        result = set_query_param("/foo/bar", "key", "value")
        assert result == "/foo/bar?key=value"

    def test_works_with_absolute_urls(self) -> None:
        result = set_query_param("https://example.com/path", "key", "value")
        assert result == "https://example.com/path?key=value"

    def test_handles_special_characters_in_values(self) -> None:
        result = set_query_param("https://example.com/path", "redirect", "https://other.com?a=1")
        assert "redirect=https%3A%2F%2Fother.com%3Fa%3D1" in result


class TestRemoveQueryParam:
    def test_remove_existing_param(self) -> None:
        result = remove_query_param("https://example.com/path?foo=bar", "foo")
        assert result == "https://example.com/path"

    def test_remove_nonexistent_param_returns_unchanged(self) -> None:
        result = remove_query_param("https://example.com/path?foo=bar", "nonexistent")
        assert result == "https://example.com/path?foo=bar"

    def test_remove_from_url_with_multiple_params(self) -> None:
        result = remove_query_param("https://example.com/path?foo=1&bar=2&baz=3", "bar")
        assert "bar=2" not in result
        assert "foo=1" in result
        assert "baz=3" in result

    def test_works_with_relative_urls(self) -> None:
        result = remove_query_param("/foo/bar?key=value", "key")
        assert result == "/foo/bar"

    def test_works_with_absolute_urls(self) -> None:
        result = remove_query_param("https://example.com/path?key=value", "key")
        assert result == "https://example.com/path"
