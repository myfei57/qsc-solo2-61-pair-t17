"""Read only projections of the cabin registry."""

from __future__ import annotations

from dataclasses import dataclass

from .model import Cabin


@dataclass(frozen=True)
class CabinState:
    """An immutable copy of one cabin."""

    id: str
    name: str
    zone: str
    partition: str
    valve_open: bool
    door_open: bool
    retired: bool
    revision: int
    labels: list[str]

    @classmethod
    def from_cabin(cls, cabin: Cabin) -> "CabinState":
        return cls(
            id=cabin.id,
            name=cabin.name,
            zone=cabin.zone,
            partition=cabin.partition,
            valve_open=cabin.valve_open,
            door_open=cabin.door_open,
            retired=cabin.retired,
            revision=cabin.revision,
            labels=list(cabin.labels),
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "name": self.name,
            "zone": self.zone,
            "partition": self.partition,
            "valve_open": self.valve_open,
            "door_open": self.door_open,
            "retired": self.retired,
            "revision": self.revision,
            "labels": self.labels,
        }


@dataclass(frozen=True)
class RegistryState:
    """Every cabin plus the active and total counts."""

    cabins: list[CabinState]
    active: int
    total: int

    def as_dict(self) -> dict[str, object]:
        return {
            "cabins": [cabin.as_dict() for cabin in self.cabins],
            "active": self.active,
            "total": self.total,
        }
