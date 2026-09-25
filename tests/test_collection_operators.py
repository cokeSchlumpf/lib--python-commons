from commons.collection_operators import ensure_immutable_unique_sequence


class TestEnsureImmutableUniqueSequence:
    def test_removes_duplicates(self):
        result = ensure_immutable_unique_sequence([1, 2, 2, 3, 3, 3])
        assert result == (1, 2, 3)

    def test_preserves_order(self):
        result = ensure_immutable_unique_sequence([3, 1, 2, 1, 3])
        assert result == (3, 1, 2)

    def test_empty_sequence(self):
        result = ensure_immutable_unique_sequence([])
        assert result == ()

    def test_no_duplicates(self):
        result = ensure_immutable_unique_sequence([1, 2, 3])
        assert result == (1, 2, 3)

    def test_all_duplicates(self):
        result = ensure_immutable_unique_sequence([1, 1, 1])
        assert result == (1,)

    def test_with_strings(self):
        result = ensure_immutable_unique_sequence(["a", "b", "a", "c"])
        assert result == ("a", "b", "c")

    def test_returns_tuple(self):
        result = ensure_immutable_unique_sequence([1, 2])
        assert isinstance(result, tuple)

    def test_input_from_tuple(self):
        result = ensure_immutable_unique_sequence((1, 2, 1))
        assert result == (1, 2)
