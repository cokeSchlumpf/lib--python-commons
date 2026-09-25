import re
from typing import Any


def deep_merge(base: dict, override: dict) -> dict:
    """
    Recursively merge two dictionaries, with override values taking precedence.

    When both base and override have a dict value for the same key, the dicts are
    merged recursively. For all other cases (non-dict values, or key only in one dict),
    the override value replaces the base value.

    Args:
        base: The base dictionary to merge into.
        override: The dictionary whose values take precedence.

    Returns:
        A new dictionary with merged values. Neither input dict is mutated.
    """
    result = base.copy()

    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value

    return result


def unflatten(data: dict[str, Any]) -> dict[str, Any]:
    """
    Convert a flat dictionary with dotted keys to a nested structure.

    Supports:
    - Dot notation: "foo.bar" -> {"foo": {"bar": ...}}
    - List indices: "items[0]" -> {"items": [...]}
    - Bracket keys: 'data["key"]' -> {"data": {"key": ...}}

    Args:
        data: A flat dictionary with dotted/bracketed keys.

    Returns:
        A nested dictionary structure.

    Raises:
        ValueError: If list indices are not contiguous (e.g., index 1 exists but index 0 is missing).
    """
    result: dict[str, Any] = {}

    for flat_key, value in data.items():
        keys = _parse_key(flat_key)
        _set_nested(result, keys, value)

    _validate_no_missing_indices(result)

    return result


def flatten(data: dict[str, Any], prefix: str = "") -> dict[str, Any]:
    """
    Convert a nested dictionary to a flat dictionary with dotted keys.

    Inverse of unflatten().

    Args:
        data: A nested dictionary structure.
        prefix: Internal prefix for recursive calls.

    Returns:
        A flat dictionary with dotted/bracketed keys.
    """
    result: dict[str, Any] = {}

    for key, value in data.items():
        if prefix:
            if _needs_bracket_notation(key):
                new_key = f'{prefix}["{key}"]'
            else:
                new_key = f"{prefix}.{key}"
        else:
            new_key = key

        if isinstance(value, dict):
            result.update(flatten(value, new_key))
        elif isinstance(value, list):
            for i, item in enumerate(value):
                if isinstance(item, dict):
                    result.update(flatten(item, f"{new_key}[{i}]"))
                else:
                    result[f"{new_key}[{i}]"] = item
        else:
            result[new_key] = value

    return result


def _parse_key(flat_key: str) -> list[str | int]:
    """Parse 'foo.bar[0]["key"]' into ['foo', 'bar', 0, 'key']."""
    pattern = r'\.?([^.\[\]]+)|\[(\d+)\]|\["([^"]+)"\]|\[\'([^\']+)\'\]'
    keys: list[str | int] = []
    for match in re.finditer(pattern, flat_key):
        if match.group(1):  # dot notation key
            keys.append(match.group(1))
        elif match.group(2):  # numeric index
            keys.append(int(match.group(2)))
        elif match.group(3):  # double-quoted key
            keys.append(match.group(3))
        elif match.group(4):  # single-quoted key
            keys.append(match.group(4))
    return keys


def _set_nested(obj: dict[str, Any] | list[Any], keys: list[str | int], value: Any) -> None:
    """Set a value in a nested structure, creating dicts/lists as needed."""
    for i, key in enumerate(keys[:-1]):
        next_key = keys[i + 1]
        if isinstance(key, int):
            # obj is a list
            while len(obj) <= key:  # type: ignore[arg-type]
                obj.append(None)  # type: ignore[union-attr]
            if obj[key] is None:  # type: ignore[index]
                obj[key] = [] if isinstance(next_key, int) else {}  # type: ignore[index]
            obj = obj[key]  # type: ignore[index, assignment]
        else:
            # obj is a dict
            if key not in obj:  # type: ignore[operator]
                obj[key] = [] if isinstance(next_key, int) else {}  # type: ignore[index, call-overload]
            obj = obj[key]  # type: ignore[index, assignment, call-overload]

    # Set final value
    final_key = keys[-1]
    if isinstance(final_key, int):
        while len(obj) <= final_key:  # type: ignore[arg-type]
            obj.append(None)  # type: ignore[union-attr]
        obj[final_key] = value  # type: ignore[index]
    else:
        obj[final_key] = value  # type: ignore[index, call-overload]


def _needs_bracket_notation(key: str) -> bool:
    """Check if key needs ["key"] notation (contains dots or special chars)."""
    return not key.isidentifier()


def _validate_no_missing_indices(obj: Any, path: str = "") -> None:
    """Recursively validate that no list has missing (None) indices."""
    if isinstance(obj, dict):
        for key, value in obj.items():
            new_path = f"{path}.{key}" if path else key
            _validate_no_missing_indices(value, new_path)
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            new_path = f"{path}[{i}]"
            if item is None:
                raise ValueError(f"Missing list index at '{new_path}'")
            _validate_no_missing_indices(item, new_path)
