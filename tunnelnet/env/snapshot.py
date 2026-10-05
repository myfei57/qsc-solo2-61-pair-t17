"""Compact environment snapshot used by the console."""

from __future__ import annotations

from .service import Environment


def snapshot(environment: Environment) -> dict[str, object]:
    """Partition, latest value and reading count for every sensor."""

    state = environment.state()
    return {
        "sensors": {key: value.as_dict() for key, value in state.sensors.items()},
        "alarms": state.alarms,
    }
