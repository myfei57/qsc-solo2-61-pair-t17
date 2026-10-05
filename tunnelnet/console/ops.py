"""Operator counters and store reset."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - imported only for type checkers
    from .runtime import Runtime


@dataclass(frozen=True)
class OpsCounters:
    """Small set of counters shown on the operator page."""

    store_records: int
    cabins: int
    access_pending: int
    drain_pits: int
    fire_alarms: int
    patrol_missed: int
    audit_records: int

    def as_dict(self) -> dict[str, int]:
        return {
            "store_records": self.store_records,
            "cabins": self.cabins,
            "access_pending": self.access_pending,
            "drain_pits": self.drain_pits,
            "fire_alarms": self.fire_alarms,
            "patrol_missed": self.patrol_missed,
            "audit_records": self.audit_records,
        }


def collect(rt: "Runtime") -> OpsCounters:
    return OpsCounters(
        store_records=rt.store.file_count(),
        cabins=rt.cabins.active_count(),
        access_pending=rt.access.summary()["pending"],
        drain_pits=rt.drain.pit_count(),
        fire_alarms=rt.fire.alarm_count(),
        patrol_missed=len(rt.patrol.missed()),
        audit_records=rt.audit.count(),
    )


def reset_store(rt: "Runtime") -> dict[str, object]:
    """Clear every persisted record, as a factory reset would."""

    for kind in rt.store.kinds():
        for record_id in rt.store.list(kind):
            rt.store.delete(kind, record_id)
    return {"reset": True, "records": rt.store.file_count()}
