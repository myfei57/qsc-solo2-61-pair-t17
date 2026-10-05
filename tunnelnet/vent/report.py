"""Read only projection of the ventilation bank."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class VentState:
    """Whether the ventilation bank is running."""

    running: bool

    @property
    def status(self) -> str:
        return "running" if self.running else "stopped"

    def as_dict(self) -> dict[str, object]:
        return {"running": self.running, "status": self.status}
