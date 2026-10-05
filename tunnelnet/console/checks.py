"""Component health checks."""

from __future__ import annotations

from typing import TYPE_CHECKING

from tunnelnet.cable import danger_count

if TYPE_CHECKING:  # pragma: no cover - imported only for type checkers
    from .runtime import Runtime


def run_checks(rt: "Runtime") -> list[dict[str, str]]:
    """Return one check row per mutable component."""

    checks: list[dict[str, str]] = [
        {
            "name": "store",
            "status": "ok",
            "detail": f"kinds={len(rt.store.kinds())} records={rt.store.file_count()}",
        }
    ]

    pending = rt.access.summary()["pending"]
    checks.append(
        {
            "name": "access",
            "status": "warn" if pending else "ok",
            "detail": f"pending requests={pending}",
        }
    )

    high = rt.drain.high_count()
    checks.append(
        {"name": "drain", "status": "warn" if high else "ok", "detail": f"high pits={high}"}
    )

    checks.append(
        {
            "name": "ventilation",
            "status": "ok" if rt.ventilation.running() else "warn",
            "detail": rt.ventilation.status(),
        }
    )

    alarms = rt.fire.alarm_count()
    checks.append(
        {"name": "fire", "status": "warn" if alarms else "ok", "detail": f"alarms={alarms}"}
    )

    missed = len(rt.patrol.missed())
    checks.append(
        {"name": "patrol", "status": "warn" if missed else "ok", "detail": f"missed={missed}"}
    )

    overage = rt.quota.overage_total()
    checks.append(
        {
            "name": "quota",
            "status": "warn" if overage > 0 else "ok",
            "detail": f"overage={overage:.4f}",
        }
    )

    danger = danger_count(rt.cables, 75.0)
    checks.append(
        {"name": "cables", "status": "warn" if danger else "ok", "detail": f"over temperature={danger}"}
    )

    env_alarms = rt.env.alarm_count()
    checks.append(
        {
            "name": "environment",
            "status": "warn" if env_alarms else "ok",
            "detail": f"alarms={env_alarms}",
        }
    )

    checks.append({"name": "audit", "status": "ok", "detail": f"records={rt.audit.count()}"})
    return checks
