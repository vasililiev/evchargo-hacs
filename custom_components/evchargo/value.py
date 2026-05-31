from __future__ import annotations

from typing import Any


def first_value(data: dict[str, Any], *paths: str) -> Any:
    """Return the first non-empty value from dotted paths."""
    for path in paths:
        current: Any = data
        found = True
        for part in path.split('.'):
            if isinstance(current, dict) and part in current:
                current = current[part]
            elif isinstance(current, list) and part.isdigit():
                index = int(part)
                if index >= len(current):
                    found = False
                    break
                current = current[index]
            else:
                found = False
                break
        if not found:
            continue
        if current not in (None, ""):
            return current
    return None


def first_dict(data: dict[str, Any], *paths: str) -> dict[str, Any]:
    value = first_value(data, *paths)
    return value if isinstance(value, dict) else {}


def first_float(data: dict[str, Any], *paths: str) -> float | None:
    value = first_value(data, *paths)
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
