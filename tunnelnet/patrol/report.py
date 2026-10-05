"""Read only projection of the patrol service."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PatrolState:
    """Route identifiers, visited identifiers and progress."""

    route: list[str]
    checked: list[str]
    missed: list[str]
    progress: float

    def as_dict(self) -> dict[str, object]:
        return {
            "route": self.route,
            "checked": self.checked,
            "missed": self.missed,
            "progress": self.progress,
        }
