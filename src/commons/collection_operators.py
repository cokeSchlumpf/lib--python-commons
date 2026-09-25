from typing import Sequence, TypeVar


T = TypeVar("T")


def ensure_immutable_sequence(seq: Sequence[T]) -> Sequence[T]:
    """Creates an imutable sequence from source sequence."""
    return tuple(seq)


def ensure_immutable_unique_sequence(seq: Sequence[T]) -> Sequence[T]:
    """Creates an immutable set as sequence from source sequence."""
    return tuple(dict.fromkeys(seq))
