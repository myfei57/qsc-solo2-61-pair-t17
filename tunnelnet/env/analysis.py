"""Pure numeric helpers for environmental trend statistics."""

from __future__ import annotations

from collections.abc import Sequence


def mean(values: Sequence[float]) -> float:
    """Arithmetic mean, or zero for an empty window."""

    if not values:
        return 0.0
    return sum(values) / len(values)


def variance(values: Sequence[float]) -> float:
    """Population variance of a window."""

    if not values:
        return 0.0
    average = mean(values)
    return sum((value - average) ** 2 for value in values) / len(values)


def standard_deviation(values: Sequence[float]) -> float:
    """Square root of :func:`variance`, computed by Newton iteration."""

    target = variance(values)
    if target <= 0:
        return 0.0
    estimate = target
    for _ in range(24):
        estimate = (estimate + target / estimate) / 2
    return estimate


def percentile(values: Sequence[float], ratio: float) -> float:
    """Nearest rank percentile, clamped to the window bounds."""

    if not values:
        return 0.0
    ordered = sorted(values)
    index = int(ratio * (len(ordered) - 1))
    if index < 0:
        index = 0
    if index >= len(ordered):
        index = len(ordered) - 1
    return ordered[index]
