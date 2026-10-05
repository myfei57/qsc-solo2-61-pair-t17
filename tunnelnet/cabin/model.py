"""Mutable cabin state held by the registry."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Cabin:
    """One tunnel cabin together with its door and inlet valve state."""

    id: str
    name: str = ""
    zone: str = ""
    partition: str = ""
    valve_open: bool = False
    door_open: bool = False
    retired: bool = False
    revision: int = 1
    labels: list[str] = field(default_factory=list)
