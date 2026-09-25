import pytest

from commons.dict_operators import deep_merge, flatten, unflatten


class TestDeepMerge:
    def test_empty_base(self):
        result = deep_merge({}, {"a": 1})
        assert result == {"a": 1}

    def test_empty_override(self):
        result = deep_merge({"a": 1}, {})
        assert result == {"a": 1}

    def test_both_empty(self):
        result = deep_merge({}, {})
        assert result == {}

    def test_non_overlapping_keys(self):
        result = deep_merge({"a": 1}, {"b": 2})
        assert result == {"a": 1, "b": 2}

    def test_overlapping_non_dict_values_override_wins(self):
        result = deep_merge({"a": 1}, {"a": 2})
        assert result == {"a": 2}

    def test_nested_dict_merging(self):
        base = {"db": {"host": "localhost", "port": 5432}}
        override = {"db": {"host": "production.example.com"}}
        result = deep_merge(base, override)
        assert result == {"db": {"host": "production.example.com", "port": 5432}}

    def test_deeply_nested_merging(self):
        base = {"a": {"b": {"c": {"d": 1, "e": 2}}}}
        override = {"a": {"b": {"c": {"d": 10}}}}
        result = deep_merge(base, override)
        assert result == {"a": {"b": {"c": {"d": 10, "e": 2}}}}

    def test_override_dict_with_non_dict(self):
        base = {"a": {"nested": "value"}}
        override = {"a": "flat"}
        result = deep_merge(base, override)
        assert result == {"a": "flat"}

    def test_override_non_dict_with_dict(self):
        base = {"a": "flat"}
        override = {"a": {"nested": "value"}}
        result = deep_merge(base, override)
        assert result == {"a": {"nested": "value"}}

    def test_mixed_keys(self):
        base = {"a": 1, "b": {"x": 10}, "c": 3}
        override = {"b": {"y": 20}, "d": 4}
        result = deep_merge(base, override)
        assert result == {"a": 1, "b": {"x": 10, "y": 20}, "c": 3, "d": 4}

    def test_does_not_mutate_base(self):
        base = {"a": {"b": 1}}
        override = {"a": {"c": 2}}
        deep_merge(base, override)
        assert base == {"a": {"b": 1}}

    def test_does_not_mutate_override(self):
        base = {"a": 1}
        override = {"b": 2}
        deep_merge(base, override)
        assert override == {"b": 2}


class TestUnflatten:
    def test_simple_dot_notation(self) -> None:
        result = unflatten({"foo.bar": 1})
        assert result == {"foo": {"bar": 1}}

    def test_multiple_keys_same_parent(self) -> None:
        result = unflatten({"a.b": 1, "a.c": 2})
        assert result == {"a": {"b": 1, "c": 2}}

    def test_list_indices(self) -> None:
        result = unflatten({"items[0]": "a", "items[1]": "b"})
        assert result == {"items": ["a", "b"]}

    def test_list_with_numeric_values(self) -> None:
        result = unflatten({"foo[0]": 42, "foo[1]": 67})
        assert result == {"foo": [42, 67]}

    def test_nested_object_in_list(self) -> None:
        result = unflatten({"a[0].name": "x"})
        assert result == {"a": [{"name": "x"}]}

    def test_multiple_objects_in_list(self) -> None:
        result = unflatten({
            "foo[0].a": 42,
            "foo[0].b": 67,
            "foo[1].a": 43,
            "foo[1].b": 68,
        })
        assert result == {"foo": [{"a": 42, "b": 67}, {"a": 43, "b": 68}]}

    def test_bracket_keys_double_quotes(self) -> None:
        result = unflatten({'data["my-key"]': 1})
        assert result == {"data": {"my-key": 1}}

    def test_bracket_keys_single_quotes(self) -> None:
        result = unflatten({"data['my-key']": 1})
        assert result == {"data": {"my-key": 1}}

    def test_mixed_notation(self) -> None:
        result = unflatten({"a.b[0].c": 1})
        assert result == {"a": {"b": [{"c": 1}]}}

    def test_empty_dict(self) -> None:
        result = unflatten({})
        assert result == {}

    def test_single_key_no_dots(self) -> None:
        result = unflatten({"foo": 1})
        assert result == {"foo": 1}

    def test_missing_list_index_raises_error(self) -> None:
        with pytest.raises(ValueError, match="Missing list index at 'items\\[1\\]'"):
            unflatten({"items[0]": "a", "items[2]": "c"})

    def test_missing_first_index_raises_error(self) -> None:
        with pytest.raises(ValueError, match="Missing list index at 'foo\\[0\\]'"):
            unflatten({"foo[1]": 42})

    def test_deeply_nested(self) -> None:
        result = unflatten({"a.b.c.d.e": 1})
        assert result == {"a": {"b": {"c": {"d": {"e": 1}}}}}


class TestFlatten:
    def test_simple_nested(self) -> None:
        result = flatten({"foo": {"bar": 1}})
        assert result == {"foo.bar": 1}

    def test_list_values(self) -> None:
        result = flatten({"items": ["a", "b"]})
        assert result == {"items[0]": "a", "items[1]": "b"}

    def test_nested_object_in_list(self) -> None:
        result = flatten({"a": [{"b": 1}]})
        assert result == {"a[0].b": 1}

    def test_special_key_chars(self) -> None:
        result = flatten({"a": {"my-key": 1}})
        assert result == {'a["my-key"]': 1}

    def test_empty_dict(self) -> None:
        result = flatten({})
        assert result == {}

    def test_flat_dict(self) -> None:
        result = flatten({"foo": 1})
        assert result == {"foo": 1}

    def test_deeply_nested(self) -> None:
        result = flatten({"a": {"b": {"c": {"d": 1}}}})
        assert result == {"a.b.c.d": 1}

    def test_mixed_types(self) -> None:
        result = flatten({"a": {"b": 1, "c": [2, 3]}})
        assert result == {"a.b": 1, "a.c[0]": 2, "a.c[1]": 3}


class TestFlattenUnflattenRoundTrip:
    def test_nested_to_flat_to_nested(self) -> None:
        original = {"a": {"b": 1, "c": [{"d": 2}]}}
        assert unflatten(flatten(original)) == original

    def test_flat_to_nested_to_flat(self) -> None:
        original = {"a.b": 1, "a.c[0].d": 2}
        assert flatten(unflatten(original)) == original

    def test_complex_structure(self) -> None:
        original = {
            "user": {
                "name": "Alice",
                "addresses": [
                    {"city": "NYC", "zip": "10001"},
                    {"city": "LA", "zip": "90001"},
                ],
            }
        }
        assert unflatten(flatten(original)) == original