"""Zone suppression log raised when a fire zone is activated."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Suppression:
    """One suppression action taken against a zone."""

    zone: str
    active: bool

    def as_dict(self) -> dict[str, object]:
        return {"zone": self.zone, "active": self.active}


class SuppressionLog:
    """Append only record of the zones that were suppressed."""

    def __init__(self) -> None:
        self._entries: list[Suppression] = []

    def activate(self, zone: str) -> Suppression:
        entry = Suppression(zone=zone, active=True)
        self._entries.append(entry)
        return entry

    def zones(self) -> list[str]:
        return [entry.zone for entry in self._entries]

    def entries(self) -> list[Suppression]:
        return list(self._entries)

    def distinct_zones(self) -> list[str]:
        seen: list[str] = []
        for zone in self.zones():
            if zone not in seen:
                seen.append(zone)
        return seen

    def count(self) -> int:
        return len(self._entries)

    def clear(self) -> None:
        self._entries = []

    def describe(self) -> str:
        return f"suppressions={self.count()} zones={len(self.distinct_zones())}"
