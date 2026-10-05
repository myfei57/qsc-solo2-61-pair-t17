"""Fire linkage service.

A smoke report closes the zone damper and stops ventilation before the zone is
linked, and every alarm is passed through a de-duplicator so a repeated event
key cannot raise a second alarm.
"""

from __future__ import annotations

from typing import Protocol

from .model import DamperState, Detector
from .report import FireReport
from .zone import activation_order


class DamperStore(Protocol):
    """Persists the closed state of a zone damper."""

    def save(self, kind: str, record_id: str, value: object) -> None:  # pragma: no cover - structural
        ...


class VentStopper(Protocol):
    """Stops the ventilation bank when smoke is confirmed."""

    def stop(self) -> bool:  # pragma: no cover - structural
        ...


class Suppressor(Protocol):
    """Activates suppression for one zone."""

    def activate(self, zone: str) -> object:  # pragma: no cover - structural
        ...


class Deduper(Protocol):
    """Records an event key, reporting whether it was new."""

    def record(self, key: str) -> bool:  # pragma: no cover - structural
        ...


class FireService:
    """Detectors, dampers, suppression and de-duplicated alarms."""

    def __init__(
        self,
        dampers: DamperStore,
        vent: VentStopper,
        suppressor: Suppressor,
        deduper: Deduper,
        zones: tuple[str, ...],
    ) -> None:
        self._dampers = dampers
        self._vent = vent
        self._suppressor = suppressor
        self._deduper = deduper
        self._zones = tuple(zones)
        self._alarms: list[str] = []
        self._detectors: dict[str, Detector] = {}

    def zones(self) -> list[str]:
        return list(self._zones)

    def zone_count(self) -> int:
        return len(self._zones)

    def add_detector(self, detector: Detector) -> Detector:
        self._detectors[detector.id] = detector
        return detector

    def detectors(self) -> list[Detector]:
        return [self._detectors[key] for key in sorted(self._detectors)]

    def detector_count(self) -> int:
        return len(self._detectors)

    def zone_of_detector(self, detector_id: str) -> str:
        detector = self._detectors.get(detector_id)
        return "" if detector is None else detector.zone

    def detect(self, detector_id: str) -> bool:
        """Treat one detector report as smoke in the detector's zone."""

        return self.handle_smoke(self.zone_of_detector(detector_id))

    def handle_smoke(self, zone: str) -> bool:
        """Close the damper and stop ventilation for the reporting zone."""

        self._dampers.save("damper", zone, DamperState(zone=zone, closed=True).as_dict())
        self._vent.stop()
        return True

    def activate_zones(self, source: str) -> list[str]:
        """Suppress the source zone first and then the adjacent zones."""

        order = activation_order(self._zones, source)
        for zone in order:
            self._suppressor.activate(zone)
        return order

    def raise_alarm(self, event_key: str) -> bool:
        """Record an alarm unless the same event key was already seen."""

        if not self._deduper.record(event_key):
            return False
        self._alarms.append(event_key)
        return True

    def alarms(self) -> list[str]:
        return list(self._alarms)

    def alarm_count(self) -> int:
        return len(self._alarms)

    def distinct_alarms(self) -> int:
        return len(set(self._alarms))

    def clear_alarms(self) -> int:
        self._alarms = []
        return self.alarm_count()

    def report(self) -> FireReport:
        return FireReport(
            detector_count=self.detector_count(),
            alarm_count=self.alarm_count(),
            zone_count=self.zone_count(),
            alarms=self.alarms(),
        )

    def describe(self) -> str:
        return (
            f"fire detectors={self.detector_count()} zones={self.zone_count()} "
            f"alarms={self.alarm_count()}"
        )
