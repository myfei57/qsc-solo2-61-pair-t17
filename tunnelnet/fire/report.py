"""Read only fire linkage report."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FireReport:
    """Detector, alarm and zone totals for the dashboard."""

    detector_count: int
    alarm_count: int
    zone_count: int
    alarms: list[str]

    def as_dict(self) -> dict[str, object]:
        return {
            "detector_count": self.detector_count,
            "alarm_count": self.alarm_count,
            "zone_count": self.zone_count,
            "alarms": self.alarms,
        }
