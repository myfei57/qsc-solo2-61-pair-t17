"""Read only projections of the environment service."""

from __future__ import annotations

from dataclasses import dataclass

from .model import Reading


@dataclass(frozen=True)
class ReadingState:
    """Latest value and count for one sensor."""

    partition: str
    latest: float
    count: int

    def as_dict(self) -> dict[str, object]:
        return {"partition": self.partition, "latest": self.latest, "count": self.count}


@dataclass(frozen=True)
class EnvironmentState:
    """Per sensor summaries plus the alarm and sample totals."""

    sensors: dict[str, ReadingState]
    alarms: int
    samples: int

    def as_dict(self) -> dict[str, object]:
        return {
            "sensors": {key: value.as_dict() for key, value in self.sensors.items()},
            "alarms": self.alarms,
            "samples": self.samples,
        }


def latest_value(readings: list[Reading]) -> float:
    if not readings:
        return 0.0
    return readings[-1].value
