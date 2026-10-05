"""Zone linkage ordering: the source zone activates before its neighbours."""

from __future__ import annotations

from collections.abc import Sequence


def adjacent_zones(zones: Sequence[str], source: str) -> list[str]:
    """Every zone except the source, nearest first and then by identifier."""

    if source not in zones:
        return sorted(zones)
    index = list(zones).index(source)
    return sorted(
        (zone for zone in zones if zone != source),
        key=lambda zone: (abs(list(zones).index(zone) - index), zone),
    )


def activation_order(zones: Sequence[str], source: str) -> list[str]:
    """The source zone followed by its neighbours in distance order."""

    neighbours = adjacent_zones(zones, source)
    if source in zones:
        return [source, *neighbours]
    return neighbours
