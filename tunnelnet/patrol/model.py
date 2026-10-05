"""Patrol check-ins and the aggregate summary."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CheckIn:
    """One cabin visit recorded by a patrol operator."""

    cabin_id: str
    at: str

    def as_dict(self) -> dict[str, str]:
        return {"cabin_id": self.cabin_id, "at": self.at}


@dataclass(frozen=True)
class PatrolSummary:
    """Route length, visited count and missed count."""

    route: int
    checked: int
    missed: int

    def as_dict(self) -> dict[str, int]:
        return {"route": self.route, "checked": self.checked, "missed": self.missed}
