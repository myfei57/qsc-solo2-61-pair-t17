"""Runtime telemetry counters."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from tunnelnet.cable import danger_count

if TYPE_CHECKING:  # pragma: no cover - imported only for type checkers
    from .runtime import Runtime


@dataclass(frozen=True)
class Telemetry:
    """A flat snapshot of the numbers an operator watches."""

    namespaces: int
    cabins: int
    active_cabins: int
    cables: int
    cable_danger: int
    pits: int
    high_pits: int
    cycles: int
    fire_detectors: int
    fire_alarms: int
    suppressed_zones: int
    patrol_route: int
    patrol_checked: int
    patrol_missed: int
    quota_allocated: float
    quota_usage: float
    quota_overage: float
    audit_records: int
    store_records: int
    vent_running: bool
    drain_state: str
    environment_alarms: int

    def as_dict(self) -> dict[str, object]:
        return {
            "namespaces": self.namespaces,
            "cabins": self.cabins,
            "active_cabins": self.active_cabins,
            "cables": self.cables,
            "cable_danger": self.cable_danger,
            "pits": self.pits,
            "high_pits": self.high_pits,
            "cycles": self.cycles,
            "fire_detectors": self.fire_detectors,
            "fire_alarms": self.fire_alarms,
            "suppressed_zones": self.suppressed_zones,
            "patrol_route": self.patrol_route,
            "patrol_checked": self.patrol_checked,
            "patrol_missed": self.patrol_missed,
            "quota_allocated": self.quota_allocated,
            "quota_usage": self.quota_usage,
            "quota_overage": self.quota_overage,
            "audit_records": self.audit_records,
            "store_records": self.store_records,
            "vent_running": self.vent_running,
            "drain_state": self.drain_state,
            "environment_alarms": self.environment_alarms,
        }


def collect(rt: "Runtime") -> Telemetry:
    """Read every counter without mutating the control state."""

    return Telemetry(
        namespaces=rt.namespaces.count(),
        cabins=rt.cabins.count(),
        active_cabins=rt.cabins.active_count(),
        cables=rt.cables.count(),
        cable_danger=danger_count(rt.cables, 75.0),
        pits=rt.drain.pit_count(),
        high_pits=rt.drain.high_count(),
        cycles=rt.drain.cycle_count(),
        fire_detectors=rt.fire.detector_count(),
        fire_alarms=rt.fire.alarm_count(),
        suppressed_zones=len(rt.suppression.distinct_zones()),
        patrol_route=rt.patrol.route_len(),
        patrol_checked=rt.patrol.checked_count(),
        patrol_missed=len(rt.patrol.missed()),
        quota_allocated=rt.quota.allocated(),
        quota_usage=rt.quota.total_usage(),
        quota_overage=rt.quota.overage_total(),
        audit_records=rt.audit.count(),
        store_records=rt.store.file_count(),
        vent_running=rt.ventilation.running(),
        drain_state=rt.drain.state_name(),
        environment_alarms=rt.env.alarm_count(),
    )
