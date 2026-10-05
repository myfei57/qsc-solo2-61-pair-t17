"""Pure helpers over the per cabin usage map."""

from __future__ import annotations

from collections.abc import Mapping


def total(usage: Mapping[str, float]) -> float:
    return sum(usage.values())


def peak(usage: Mapping[str, float]) -> float:
    return max(usage.values()) if usage else 0.0


def rank(usage: Mapping[str, float]) -> list[str]:
    """Cabin identifiers from the highest usage to the lowest."""

    return sorted(usage, key=lambda cabin_id: (-usage[cabin_id], cabin_id))
