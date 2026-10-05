"""Aggregate statistics over the sump pits."""

from __future__ import annotations

from collections.abc import Sequence


def average_level(levels: Sequence[float]) -> float:
    if not levels:
        return 0.0
    return sum(levels) / len(levels)


def max_level(levels: Sequence[float]) -> float:
    if not levels:
        return 0.0
    return max(levels)


def high_count(levels: Sequence[float], threshold: float) -> int:
    return sum(1 for level in levels if level >= threshold)


def low_count(levels: Sequence[float], threshold: float) -> int:
    return sum(1 for level in levels if level < threshold)
