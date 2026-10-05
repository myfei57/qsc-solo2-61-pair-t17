"""Aggregate cabin status counters."""

from __future__ import annotations

from dataclasses import dataclass

from .registry import Registry


@dataclass(frozen=True)
class StatusSummary:
    """How many cabins exist and how many doors or valves are open."""

    total: int
    active: int
    open_doors: int
    open_valves: int

    def as_dict(self) -> dict[str, int]:
        return {
            "total": self.total,
            "active": self.active,
            "open_doors": self.open_doors,
            "open_valves": self.open_valves,
        }


def status_summary(registry: Registry) -> StatusSummary:
    cabins = registry.all()
    return StatusSummary(
        total=len(cabins),
        active=sum(1 for cabin in cabins if not cabin.retired),
        open_doors=sum(1 for cabin in cabins if cabin.door_open),
        open_valves=sum(1 for cabin in cabins if cabin.valve_open),
    )
