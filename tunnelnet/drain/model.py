"""Sump pits and the drain cycles recorded against them."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Pit:
    """One sump pit and its current water level."""

    id: str
    cabin: str = ""
    water_level: float = 0.0


@dataclass(frozen=True)
class DrainCycle:
    """One completed drain run for a cabin."""

    cabin_id: str
    started_at: str

    def as_dict(self) -> dict[str, str]:
        return {"cabin_id": self.cabin_id, "started_at": self.started_at}
