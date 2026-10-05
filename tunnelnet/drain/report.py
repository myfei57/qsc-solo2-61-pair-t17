"""Read only projections of the drain service."""

from __future__ import annotations

from dataclasses import dataclass

from .model import DrainCycle, Pit


@dataclass(frozen=True)
class PitState:
    """An immutable copy of one pit."""

    id: str
    cabin: str
    water_level: float

    def as_dict(self) -> dict[str, object]:
        return {"id": self.id, "cabin": self.cabin, "water_level": self.water_level}


@dataclass(frozen=True)
class DrainState:
    """Pits, cycles and the level threshold that decides a high pit."""

    pits: list[PitState]
    cycles: list[DrainCycle]
    threshold: float
    runs: int

    def as_dict(self) -> dict[str, object]:
        return {
            "pits": [pit.as_dict() for pit in self.pits],
            "cycles": [cycle.as_dict() for cycle in self.cycles],
            "threshold": self.threshold,
            "runs": self.runs,
        }


def pit_state(pit: Pit) -> PitState:
    return PitState(id=pit.id, cabin=pit.cabin, water_level=pit.water_level)
