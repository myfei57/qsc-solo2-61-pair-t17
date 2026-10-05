"""Read only projections of the cable registry."""

from __future__ import annotations

from dataclasses import dataclass

from .model import Cable


@dataclass(frozen=True)
class CableState:
    """An immutable copy of one cable."""

    id: str
    cabin: str
    temp: float
    status: str

    def as_dict(self) -> dict[str, object]:
        return {"id": self.id, "cabin": self.cabin, "temp": self.temp, "status": self.status}


@dataclass(frozen=True)
class CableSummary:
    """Cable count together with how many samples were taken."""

    total: int
    samples: int

    def as_dict(self) -> dict[str, int]:
        return {"total": self.total, "samples": self.samples}


def cable_state(cable: Cable) -> CableState:
    return CableState(id=cable.id, cabin=cable.cabin, temp=cable.temp, status=cable.status)
