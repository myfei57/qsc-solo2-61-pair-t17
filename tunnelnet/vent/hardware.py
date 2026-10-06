"""Fan hardware boundary.

The coordinator talks only to the :class:`FanBay` protocol: it reads feedback
once per tick and issues start/stop/open/close commands. :class:`SimulatedBay`
is the deterministic stand-in used by the offline console and the test suite;
a real deployment supplies a driver that maps the same calls onto contactors,
VFDs and damper actuators.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .model import DAMPER_TRAVEL, ROLES


@dataclass(frozen=True)
class FanFeedback:
    """Hard-wired feedback read from one fan branch."""

    run: bool = False            # run feedback (auxiliary contact / airflow switch)
    damper_open: bool = False    # damper open limit switch
    damper_closed: bool = False  # damper closed limit switch
    thermal: bool = False        # thermal / overload relay tripped
    local_stop: bool = False     # local emergency stop / maintenance isolation
    contactor_welded: bool = False  # stop commanded but the contactor stayed made


class FanBay(Protocol):
    """Physical fan and damper hardware for both branches."""

    def feedback(self, role: str) -> FanFeedback:  # pragma: no cover - structural
        ...

    def start(self, role: str) -> None:  # pragma: no cover - structural
        ...

    def stop(self, role: str) -> None:  # pragma: no cover - structural
        ...

    def open_damper(self, role: str) -> None:  # pragma: no cover - structural
        ...

    def close_damper(self, role: str) -> None:  # pragma: no cover - structural
        ...


@dataclass
class _SimFan:
    command: str = "stop"
    damper_command: str = "close"
    run: bool = False
    contactor_welded: bool = False
    fail_start: bool = False
    thermal: bool = False
    local_stop: bool = False
    broken_damper: bool = False
    damper_pos: float = 0.0  # 0 = closed, travel = open


class SimulatedBay:
    """Deterministic hardware: dampers travel, fans ramp, faults are injectable.

    Time is advanced explicitly with :meth:`advance`, so tests and the offline
    console stay reproducible. Damper limit switches only report once travel
    finishes, exactly like real end-position switches.
    """

    def __init__(self, travel: float = DAMPER_TRAVEL) -> None:
        self._travel = travel
        self._now = 0.0
        self._fans = {role: _SimFan() for role in ROLES}

    @property
    def now(self) -> float:
        return self._now

    def advance(self, seconds: float = 1.0) -> float:
        """Move the simulated clock and settle all actuators."""

        self._now += seconds
        for fan in self._fans.values():
            self._update_fan(fan)
            self._update_damper(fan)
        return self._now

    # --- fault injection (test/commissioning hooks) ----------------------

    def break_fan(self, role: str, *, welded: bool = False) -> None:
        """Kill the fan; ``welded`` simulates a contactor that will not open."""

        fan = self._fans[role]
        fan.fail_start = True
        if welded:
            fan.contactor_welded = True
            fan.run = True
        else:
            fan.run = False

    def heal_fan(self, role: str) -> None:
        """Clear every injected fault on a branch."""

        fan = self._fans[role]
        fan.fail_start = False
        fan.contactor_welded = False
        fan.broken_damper = False
        fan.thermal = False
        fan.local_stop = False
        fan.run = fan.command == "start"

    def trip_thermal(self, role: str) -> None:
        fan = self._fans[role]
        fan.thermal = True
        fan.run = False

    def isolate(self, role: str, isolated: bool = True) -> None:
        fan = self._fans[role]
        fan.local_stop = isolated
        if isolated:
            fan.run = False

    def break_damper(self, role: str) -> None:
        self._fans[role].broken_damper = True

    # --- FanBay interface -------------------------------------------------

    def feedback(self, role: str) -> FanFeedback:
        fan = self._fans[role]
        if fan.contactor_welded:
            return FanFeedback(run=True, contactor_welded=True)
        reached_open = fan.damper_pos >= self._travel
        reached_closed = fan.damper_pos <= 0.0
        return FanFeedback(
            run=fan.run,
            damper_open=reached_open,
            damper_closed=reached_closed,
            thermal=fan.thermal,
            local_stop=fan.local_stop,
        )

    def start(self, role: str) -> None:
        fan = self._fans[role]
        fan.command = "start"
        fan.run = not (fan.fail_start or fan.thermal or fan.local_stop)

    def stop(self, role: str) -> None:
        fan = self._fans[role]
        fan.command = "stop"
        if not fan.contactor_welded:
            fan.run = False

    def open_damper(self, role: str) -> None:
        self._fans[role].damper_command = "open"

    def close_damper(self, role: str) -> None:
        self._fans[role].damper_command = "close"

    # --- internals --------------------------------------------------------

    def _update_fan(self, fan: _SimFan) -> None:
        if fan.contactor_welded:
            fan.run = True
            return
        if fan.command == "start":
            fan.run = not (fan.fail_start or fan.thermal or fan.local_stop)
        else:
            fan.run = False

    def _update_damper(self, fan: _SimFan) -> None:
        if fan.broken_damper:
            return
        target = self._travel if fan.damper_command == "open" else 0.0
        step = 1.0
        if fan.damper_pos < target:
            fan.damper_pos = min(target, fan.damper_pos + step)
        elif fan.damper_pos > target:
            fan.damper_pos = max(target, fan.damper_pos - step)
