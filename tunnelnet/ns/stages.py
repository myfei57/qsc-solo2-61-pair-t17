"""Named stages of the tunnel control chain."""

from __future__ import annotations

from enum import Enum


class Stage(str, Enum):
    """A single control step on the tunnel chain."""

    ACCESS = "access"
    ENVIRONMENT = "environment"
    VENTILATION = "ventilation"
    FIRE = "fire"
    PATROL = "patrol"
    ENERGY = "energy"
    AUDIT = "audit"

    def __str__(self) -> str:
        return self.value
