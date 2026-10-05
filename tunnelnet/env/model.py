"""Environmental readings and alarms."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Reading:
    """One sensor observation."""

    sensor_id: str
    value: float
    at: str

    def as_dict(self) -> dict[str, object]:
        return {"sensor_id": self.sensor_id, "value": self.value, "at": self.at}


@dataclass(frozen=True)
class Alarm:
    """An alarm raised from a filtered reading."""

    sensor_id: str
    value: float

    def as_dict(self) -> dict[str, object]:
        return {"sensor_id": self.sensor_id, "value": self.value}
