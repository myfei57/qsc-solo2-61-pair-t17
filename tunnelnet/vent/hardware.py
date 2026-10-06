"""Fan and path damper actuators driven by the ventilation service.

These are the simulated field devices. Every command reports whether the
actuator reached the commanded state: a fan whose start coil has failed, or a
damper whose limit switch never closes, answers ``False`` and the orchestrator
treats that as a failed step that must be compensated.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass

from .policy import PRIMARY, STANDBY


class FanUnit:
    """One fan with a running coil and an independent failure flag."""

    def __init__(self, role: str) -> None:
        self.role = role
        self._lock = threading.RLock()
        self._running = False
        self._failed = False
        self._starts = 0
        self._stops = 0

    def start(self) -> bool:
        with self._lock:
            self._starts += 1
            if not self._failed:
                self._running = True
            return self._running

    def stop(self) -> bool:
        with self._lock:
            self._stops += 1
            self._running = False
            return True

    def running(self) -> bool:
        with self._lock:
            return self._running

    def set_fault(self, failed: bool = True) -> None:
        """Break or repair the fan. A broken fan also drops out."""

        with self._lock:
            self._failed = failed
            if failed:
                self._running = False

    def failed(self) -> bool:
        with self._lock:
            return self._failed

    def starts(self) -> int:
        with self._lock:
            return self._starts

    def stops(self) -> int:
        with self._lock:
            return self._stops

    def snapshot(self) -> "FanSnapshot":
        with self._lock:
            return FanSnapshot(
                role=self.role,
                running=self._running,
                failed=self._failed,
                starts=self._starts,
                stops=self._stops,
            )


class DamperUnit:
    """One air path damper with an open/closed limit switch."""

    def __init__(self, role: str) -> None:
        self.role = role
        self._lock = threading.RLock()
        self._open = False
        self._failed = False
        self._opens = 0
        self._closes = 0

    def open(self) -> bool:
        with self._lock:
            self._opens += 1
            if not self._failed:
                self._open = True
            return self._open

    def close(self) -> bool:
        with self._lock:
            self._closes += 1
            if not self._failed:
                self._open = False
            return not self._open

    def is_open(self) -> bool:
        with self._lock:
            return self._open

    def set_fault(self, failed: bool = True) -> None:
        with self._lock:
            self._failed = failed

    def failed(self) -> bool:
        with self._lock:
            return self._failed

    def opens(self) -> int:
        with self._lock:
            return self._opens

    def closes(self) -> int:
        with self._lock:
            return self._closes

    def snapshot(self) -> "DamperSnapshot":
        with self._lock:
            return DamperSnapshot(
                role=self.role,
                open=self._open,
                failed=self._failed,
                opens=self._opens,
                closes=self._closes,
            )


@dataclass(frozen=True)
class FanSnapshot:
    """Read only view of one fan actuator."""

    role: str
    running: bool
    failed: bool
    starts: int
    stops: int

    def as_dict(self) -> dict[str, object]:
        return {
            "role": self.role,
            "running": self.running,
            "failed": self.failed,
            "starts": self.starts,
            "stops": self.stops,
        }


@dataclass(frozen=True)
class DamperSnapshot:
    """Read only view of one path damper."""

    role: str
    open: bool
    failed: bool
    opens: int
    closes: int

    def as_dict(self) -> dict[str, object]:
        return {
            "role": self.role,
            "open": self.open,
            "failed": self.failed,
            "opens": self.opens,
            "closes": self.closes,
        }


class Hardware:
    """The paired fans and paired path dampers behind one ventilation bank."""

    def __init__(
        self,
        primary_fan: FanUnit | None = None,
        standby_fan: FanUnit | None = None,
        primary_damper: DamperUnit | None = None,
        standby_damper: DamperUnit | None = None,
    ) -> None:
        self._fans = {
            PRIMARY: primary_fan or FanUnit(PRIMARY),
            STANDBY: standby_fan or FanUnit(STANDBY),
        }
        self._dampers = {
            PRIMARY: primary_damper or DamperUnit(PRIMARY),
            STANDBY: standby_damper or DamperUnit(STANDBY),
        }

    def fan(self, role: str) -> FanUnit:
        return self._fans[role]

    def damper(self, role: str) -> DamperUnit:
        return self._dampers[role]

    def stop_all(self) -> bool:
        """Close both paths and stop both fans; report whether it is safe."""

        for role in (PRIMARY, STANDBY):
            self._fans[role].stop()
            self._dampers[role].close()
        return self.is_safe()

    def is_safe(self) -> bool:
        """Every fan stopped and every air path closed."""

        return not any(fan.running() for fan in self._fans.values()) and not any(
            damper.is_open() for damper in self._dampers.values()
        )

    def fans(self) -> list[FanSnapshot]:
        return [self._fans[PRIMARY].snapshot(), self._fans[STANDBY].snapshot()]

    def dampers(self) -> list[DamperSnapshot]:
        return [self._dampers[PRIMARY].snapshot(), self._dampers[STANDBY].snapshot()]
