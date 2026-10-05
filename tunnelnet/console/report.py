"""Plain text control report and the dashboard projection."""

from __future__ import annotations

from typing import TYPE_CHECKING

from tunnelnet.cable import danger_count, healthy_count, load_factor
from tunnelnet.cabin import status_summary
from tunnelnet.ns import Stage, control_chain

from .describe import collect as collect_describe
from .telemetry import collect as collect_telemetry

if TYPE_CHECKING:  # pragma: no cover - imported only for type checkers
    from .runtime import Runtime


def text_report(rt: "Runtime") -> str:
    """Render the operator report that mirrors the JSON snapshot."""

    describe = collect_describe(rt)
    telemetry = collect_telemetry(rt)
    line = control_chain()
    rows = [
        "tunnelnet control report",
        f"chain: {describe['chain']}",
        f"chain stages={line.count()} contains_fire={line.contains(Stage.FIRE)}",
        f"store: {describe['store']}",
        f"namespaces: {describe['namespaces']}",
        f"cabins: {describe['cabins']}",
        f"partitions: {describe['partitions']}",
        f"access: {describe['access']}",
        f"environment: {describe['environment']}",
        f"drain: {describe['drain']}",
        f"ventilation: {describe['ventilation']}",
        f"fire: {describe['fire']}",
        f"patrol: {describe['patrol']}",
        f"quota: {describe['quota']}",
        f"cables: {describe['cables']}",
        f"suppression: {describe['suppression']}",
        f"audit: {describe['audit']}",
        f"cable danger={telemetry.cable_danger} load_factor={load_factor(rt.cables):.4f}",
        f"drain pits={telemetry.pits} high={telemetry.high_pits} cycles={telemetry.cycles}",
        (
            f"patrol route={telemetry.patrol_route} checked={telemetry.patrol_checked} "
            f"missed={telemetry.patrol_missed}"
        ),
        f"quota allocated={telemetry.quota_allocated:.4f} usage={telemetry.quota_usage:.4f}",
        f"fire detectors={telemetry.fire_detectors} alarms={telemetry.fire_alarms}",
        f"store records={telemetry.store_records}",
    ]
    return "\n".join(rows) + "\n"


def dashboard(rt: "Runtime") -> dict[str, object]:
    """Structured dashboard report used by the JSON API."""

    fire_report = rt.fire.report()
    quota_report = rt.quota.report()
    return {
        "namespaces": {"count": rt.namespaces.count()},
        "cabins": status_summary(rt.cabins).as_dict(),
        "cables": {
            "count": rt.cables.count(),
            "load_factor": load_factor(rt.cables),
            "danger": danger_count(rt.cables, 75.0),
            "healthy": healthy_count(rt.cables, 75.0),
        },
        "drain": {
            "pits": rt.drain.pit_count(),
            "average_level": rt.drain.average_level(),
            "max_level": rt.drain.max_level(),
            "high": rt.drain.high_count(),
            "low": rt.drain.low_count(),
            "cycles": rt.drain.cycle_count(),
        },
        "fire": {
            "detectors": fire_report.detector_count,
            "alarms": fire_report.alarm_count,
            "zones": fire_report.zone_count,
        },
        "patrol": {
            "route": rt.patrol.route_len(),
            "checked": rt.patrol.checked_count(),
            "missed": len(rt.patrol.missed()),
            "progress": rt.patrol.progress(),
        },
        "quota": {
            "allocated": quota_report.allocated,
            "usage_total": quota_report.usage_total,
            "overage_total": quota_report.overage_total,
            "peak_cabin": quota_report.peak_cabin,
        },
        "audit": {"count": rt.audit.count(), "by_event": rt.audit.summary()},
        "access": rt.access.summary(),
    }
