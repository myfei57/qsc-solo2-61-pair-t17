"""Deterministic offline control ticks."""

from __future__ import annotations

from dataclasses import dataclass, field

from tunnelnet.ns import control_chain

from .http import Request, Response, json_response
from .runtime import Runtime

DEFAULT_TICKS = 5
MAX_TICKS = 100


@dataclass(frozen=True)
class Tick:
    """One simulated control step."""

    index: int
    stage: str
    environment_average: float
    drain_high: int
    patrol_missed: int
    quota_overage: float
    fire_alarms: int
    audit_records: int

    def as_dict(self) -> dict[str, object]:
        return {
            "index": self.index,
            "stage": self.stage,
            "environment_average": self.environment_average,
            "drain_high": self.drain_high,
            "patrol_missed": self.patrol_missed,
            "quota_overage": self.quota_overage,
            "fire_alarms": self.fire_alarms,
            "audit_records": self.audit_records,
        }


@dataclass(frozen=True)
class SimulationReport:
    """The full sequence plus closing counters."""

    ticks: list[Tick] = field(default_factory=list)
    final_audit_count: int = 0
    last_stage: str = ""

    def as_dict(self) -> dict[str, object]:
        return {
            "ticks": [tick.as_dict() for tick in self.ticks],
            "final_audit_count": self.final_audit_count,
            "last_stage": self.last_stage,
        }


def run_simulation(rt: Runtime, request: Request) -> Response:
    """Run a bounded number of ticks so the console can be exercised offline."""

    ticks = request.int_field("ticks", DEFAULT_TICKS)
    if ticks <= 0:
        ticks = DEFAULT_TICKS
    if ticks > MAX_TICKS:
        ticks = MAX_TICKS

    cabin_id = request.str_field("cabin_id", "cabin-1")
    sensor_id = request.str_field("sensor_id", "sensor-1")
    chain = control_chain()
    stages = chain.stages

    steps: list[Tick] = []
    for index in range(ticks):
        rt.quota.add_usage(cabin_id, float(index + 1))
        steps.append(
            Tick(
                index=index,
                stage=stages[index % chain.count()].value,
                environment_average=rt.env.average(sensor_id),
                drain_high=rt.drain.high_count(),
                patrol_missed=len(rt.patrol.missed()),
                quota_overage=rt.quota.overage(cabin_id),
                fire_alarms=rt.fire.alarm_count(),
                audit_records=rt.audit.count(),
            )
        )

    last = chain.last()
    report = SimulationReport(
        ticks=steps,
        final_audit_count=rt.audit.count(),
        last_stage="" if last is None else last.value,
    )
    return json_response(report.as_dict())
