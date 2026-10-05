"""Single source of truth for the console route table."""

from __future__ import annotations

from dataclasses import dataclass
from types import ModuleType

from .http import Router


@dataclass(frozen=True)
class Route:
    """One console endpoint and the handler attribute that serves it."""

    method: str
    path: str
    note: str
    handler: str

    def as_dict(self) -> dict[str, str]:
        return {"method": self.method, "path": self.path, "note": self.note}


def route_table() -> list[Route]:
    """Every route the console serves, in catalog order."""

    return [
        Route("GET", "/api/health", "service health and persisted records", "health"),
        Route("GET", "/api/health/checks", "detailed component health checks", "health_checks"),
        Route("GET", "/api/snapshot", "full component snapshot", "snapshot"),
        Route("GET", "/api/describe", "human readable component summary", "describe"),
        Route("GET", "/api/report", "control dashboard report", "report"),
        Route("GET", "/api/report.txt", "plain text control report", "report_text"),
        Route("GET", "/api/chain", "control chain stages", "chain"),
        Route("GET", "/api/catalog", "list all HTTP routes", "catalog"),
        Route("GET", "/api/ops", "operator counters", "ops_counters"),
        Route("POST", "/api/ops/reset-store", "factory reset persisted records", "ops_reset_store"),
        Route("GET", "/api/telemetry", "runtime telemetry counters", "telemetry"),
        Route("GET", "/api/version", "build version information", "version"),
        Route("GET", "/api/system", "runtime system information", "system"),
        Route("GET", "/api/metrics", "console request counters", "metrics"),
        Route("POST", "/api/metrics/reset", "reset console request counters", "metrics_reset"),
        Route("GET", "/api/namespaces", "namespace segments", "namespaces_list"),
        Route("POST", "/api/namespaces", "add or remove a namespace segment", "namespace_ops"),
        Route("GET", "/api/cabins", "all cabins", "cabins_list"),
        Route("GET", "/api/cabins/status", "cabin status summary", "cabin_status"),
        Route("GET", "/api/cabins/zones", "zones and cabins in a zone", "cabin_zones"),
        Route("POST", "/api/cabins/extend", "register a new cabin", "cabin_extend"),
        Route("POST", "/api/cabins/rename", "rename a cabin", "cabin_rename"),
        Route("POST", "/api/cabins/move", "move a cabin to a zone and partition", "cabin_move"),
        Route("POST", "/api/cabins/zone", "assign a cabin zone", "cabin_zone"),
        Route("POST", "/api/cabins/door", "release or seal a cabin door", "cabin_door"),
        Route("POST", "/api/cabins/valve", "open or close a cabin inlet valve", "cabin_valve"),
        Route("POST", "/api/cabins/label", "add a cabin label", "cabin_label"),
        Route("POST", "/api/cabins/retire", "retire a cabin", "cabin_retire"),
        Route("GET", "/api/access/requests", "pending entry requests", "access_requests"),
        Route("GET", "/api/access/summary", "request counters", "access_summary"),
        Route("GET", "/api/access/approvals", "durable approvals", "access_approvals"),
        Route("POST", "/api/access/submit", "submit an entry request", "access_submit"),
        Route("POST", "/api/access/grant", "grant a pending request", "access_grant"),
        Route("POST", "/api/access/approve", "approve and release a cabin door", "access_approve"),
        Route("POST", "/api/access/revoke", "revoke a durable approval", "access_revoke"),
        Route("GET", "/api/env", "environment alarms and routing", "env_overview"),
        Route("GET", "/api/env/sensors", "sensors and snapshot", "env_sensors"),
        Route("GET", "/api/env/trend", "sensor trend statistics", "env_trend"),
        Route("GET", "/api/env/threshold", "current alarm threshold", "env_threshold"),
        Route("GET", "/api/env/filter", "alarm filter window", "env_filter"),
        Route("POST", "/api/env/sample", "record a sensor reading", "env_sample"),
        Route("POST", "/api/env/partition", "repartition a sensor partition", "env_partition"),
        Route("POST", "/api/env/threshold", "set the alarm threshold", "env_threshold_set"),
        Route("POST", "/api/env/filter/reset", "clear the alarm filter window", "env_filter_reset"),
        Route("GET", "/api/drain/pits", "sump pits and levels", "drain_pits"),
        Route("GET", "/api/drain/high", "high pits and cycles", "drain_high"),
        Route("GET", "/api/drain/state", "drain state and pump runs", "drain_state"),
        Route("GET", "/api/drain/pending", "in-flight drain commands", "drain_pending"),
        Route("POST", "/api/drain/pit", "add a sump pit", "drain_pit"),
        Route("POST", "/api/drain/levels", "set pit levels", "drain_levels"),
        Route("POST", "/api/drain/start", "open valve then start the pump", "drain_start"),
        Route("POST", "/api/drain/execute", "run a de-duplicated drain command", "drain_execute"),
        Route("POST", "/api/drain/threshold", "set the pit level threshold", "drain_threshold"),
        Route("POST", "/api/drain/cycle", "record a drain cycle", "drain_cycle"),
        Route("POST", "/api/drain/state", "set the drain state label", "drain_state_set"),
        Route("POST", "/api/drain/in-flight", "mark or clear an in-flight command", "drain_in_flight"),
        Route("GET", "/api/vent", "ventilation state", "vent_state"),
        Route("POST", "/api/vent/toggle", "toggle the ventilation bank", "vent_toggle"),
        Route("POST", "/api/vent/start", "start the ventilation bank", "vent_start"),
        Route("GET", "/api/fire/detectors", "fire detectors", "fire_detectors"),
        Route("GET", "/api/fire/zones", "fire zones", "fire_zones"),
        Route("GET", "/api/fire/alarms", "fire alarms", "fire_alarms"),
        Route("GET", "/api/fire/report", "fire linkage report", "fire_report"),
        Route("POST", "/api/fire/detector", "add a fire detector", "fire_detector_add"),
        Route("POST", "/api/fire/detect", "report a detector alarm", "fire_detect"),
        Route("POST", "/api/fire/smoke", "handle smoke in a zone", "fire_smoke"),
        Route("POST", "/api/fire/zone", "link a fire zone", "fire_zone"),
        Route("POST", "/api/fire/alarm", "raise a de-duplicated alarm", "fire_alarm"),
        Route("POST", "/api/fire/clear", "clear fire alarms", "fire_clear"),
        Route("GET", "/api/patrols", "patrol route and check-ins", "patrols"),
        Route("GET", "/api/patrol/progress", "patrol progress and overdue", "patrol_progress"),
        Route("GET", "/api/patrol/summary", "patrol counters", "patrol_summary"),
        Route("POST", "/api/patrol/checkin", "record a patrol check-in", "patrol_checkin"),
        Route("POST", "/api/patrol/rebuild", "rebuild the route from cabins", "patrol_rebuild"),
        Route("POST", "/api/patrol/due", "set a cabin due time", "patrol_due"),
        Route("GET", "/api/cables", "cables and summary", "cables_list"),
        Route("GET", "/api/cables/stats", "cable temperature statistics", "cable_stats"),
        Route("GET", "/api/cables/health", "danger and healthy counts", "cable_health"),
        Route("POST", "/api/cables/temp", "set a cable temperature", "cable_temp"),
        Route("POST", "/api/cables/sample", "sample a cable temperature", "cable_sample"),
        Route("GET", "/api/quota/report", "baseline allocation report", "quota_report"),
        Route("GET", "/api/quota/usage", "usage per cabin", "quota_usage"),
        Route("GET", "/api/quota/advanced", "overage and forecast", "quota_advanced"),
        Route("GET", "/api/quota/summary", "quota report", "quota_summary"),
        Route("POST", "/api/quota/refresh", "refresh the cabin baselines", "quota_refresh"),
        Route("POST", "/api/quota/usage", "add cabin usage", "quota_add_usage"),
        Route("GET", "/api/audit", "audit records", "audit_list"),
        Route("GET", "/api/audit/query", "query audit records", "audit_query"),
        Route("GET", "/api/audit/summary", "audit counters", "audit_summary"),
        Route("GET", "/api/audit/marks", "de-duplication marks", "audit_marks"),
        Route("POST", "/api/audit/append", "append an audit record", "audit_append"),
        Route("POST", "/api/audit/clear", "clear audit records", "audit_clear"),
        Route("POST", "/api/audit/marks/clear", "clear de-duplication marks", "audit_marks_clear"),
        Route("GET", "/api/suppression", "suppressed zones", "suppression_list"),
        Route("POST", "/api/suppression/clear", "clear the suppression log", "suppression_clear"),
        Route("GET", "/api/store/stats", "record counts per kind", "store_stats"),
        Route("GET", "/api/store/export", "export stored records", "store_export"),
        Route("POST", "/api/cycle", "run one full control cycle", "cycle"),
        Route("POST", "/api/simulate", "run deterministic simulation ticks", "simulate"),
        Route("GET", "/api/export/audit", "audit trail as CSV", "export_audit"),
        Route("GET", "/api/export/telemetry", "telemetry counters as CSV", "export_telemetry"),
        Route("GET", "/api/export/store", "store record counts as CSV", "export_store"),
    ]


def register_routes(router: Router, handlers: ModuleType) -> None:
    """Bind every catalogued route to its handler function."""

    for route in route_table():
        router.add(route.method, route.path, getattr(handlers, route.handler))
