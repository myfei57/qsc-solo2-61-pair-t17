"""Primary/standby fan bank domain model.

Two fans share one duct. Only one fan is ever allowed to run and at most one
branch damper is ever open, enforced by the coordinator state machine (and in a
real installation by a hardware/electrical interlock wired the same way).
"""

from __future__ import annotations

from dataclasses import dataclass, field

# --- roles ----------------------------------------------------------------

PRIMARY = "primary"
STANDBY = "standby"
ROLES = (PRIMARY, STANDBY)


def other_role(role: str) -> str:
    """The mate of a fan role."""

    return STANDBY if role == PRIMARY else PRIMARY


# --- timing (seconds of simulated/monotonic time) -------------------------

DAMPER_TRAVEL = 2.0
START_CONFIRM = 3.0
STOP_CONFIRM = 3.0
FAULT_DEBOUNCE = 2.0
SWITCH_COOLDOWN = 30.0
# A running fan that loses its run feedback for this long is treated as dead.
RUN_LOSS_CONFIRM = 2.0

# Automatic failover flapping guard: at most this many automatic switches per
# window; exceeding it parks the bank in the safe state until manual reset.
AUTO_SWITCH_LIMIT = 3
AUTO_SWITCH_WINDOW = 600.0


# --- per-fan state --------------------------------------------------------

@dataclass
class FanState:
    """State machine for one fan and its branch damper.

    The fan itself is STARTING / RUNNING / STOPPING / STOPPED / FAULTED.
    ``damper`` is OPENING / OPEN / CLOSING / CLOSED independently, because the
    damper travels while the fan is stopped.
    """

    role: str
    fan: str = "stopped"
    damper: str = "closed"
    fault: str = ""
    damper_fault: str = ""
    since: float = 0.0
    # Monotonic deadline for the action currently being confirmed (0 = none).
    deadline: float = 0.0
    # Transient loss of run feedback (debounced before declaring a fault).
    run_lost_at: float = -1.0

    def healthy(self) -> bool:
        """A fan is a usable standby only when it and its damper are healthy."""

        return self.fault == "" and self.damper_fault == "" and self.fan != "faulted"

    def is_running(self) -> bool:
        return self.fan == "running"

    def as_dict(self) -> dict[str, object]:
        return {
            "role": self.role,
            "fan": self.fan,
            "damper": self.damper,
            "fault": self.fault,
            "damper_fault": self.damper_fault,
            "healthy": self.healthy(),
            "running": self.is_running(),
        }


# --- group state ----------------------------------------------------------

# Normal modes:
#   stopped    - intentionally off (both fans stopped, both dampers closed)
#   running    - serving air with one fan (see active_role / preferred_role)
#   switching  - a switchover saga is in progress
#   safe       - failed to a safe state: everything stopped/closed, latched
#   smoke      - smoke linkage latched: ventilation held down until reset
MODE_STOPPED = "stopped"
MODE_RUNNING = "running"
MODE_SWITCHING = "switching"
MODE_SAFE = "safe"
MODE_SMOKE = "smoke"

# Why the bank is parked in ``safe``.
SAFE_NO_HEALTHY = "no_healthy_fan"
SAFE_SWITCH_FAILED = "switchover_failed"
SAFE_ROLLBACK_FAILED = "rollback_failed"
SAFE_FLAP = "auto_switch_limit"
SAFE_WELDED = "contactor_welded"
SAFE_DAMPER = "damper_fault"


@dataclass
class SwitchSaga:
    """A break-before-make switchover, persisted so it survives a restart.

    Phases, in order:
        stop_old    - stop command issued, waiting for the old fan to stop
        close_old   - old fan stopped, closing the old branch damper
        open_new    - old damper closed, opening the new branch damper
        start_new   - new damper open, start command issued, awaiting run fb
        done        - finished
        rolled_back - compensation restored the previous duty fan
        failed      - could neither finish nor roll back (bank goes safe)
    """

    id: str
    from_role: str
    to_role: str
    automatic: bool
    phase: str = "stop_old"
    since: float = 0.0
    deadline: float = 0.0
    attempts: int = 0
    # For a planned (manual) switch we compensate back to the old duty fan;
    # for an automatic (fault driven) one there is nothing to roll back to.
    rollback_role: str = ""

    def active(self) -> bool:
        return self.phase not in ("done", "rolled_back", "failed")

    def as_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "from": self.from_role,
            "to": self.to_role,
            "automatic": self.automatic,
            "phase": self.phase,
            "attempts": self.attempts,
            "rollback_role": self.rollback_role,
        }


@dataclass
class GroupState:
    """Everything the coordinator must persist between ticks."""

    mode: str = MODE_STOPPED
    preferred_role: str = PRIMARY
    active_role: str = ""
    safe_reason: str = ""
    smoke: bool = False
    smoke_zone: str = ""
    switch: SwitchSaga | None = None
    auto_switches: list[float] = field(default_factory=list)
    last_switch_at: float = -1.0
    # Last command actually issued per fan, for output reconciliation on boot.
    last_fan_cmd: dict[str, str] = field(default_factory=lambda: {PRIMARY: "stop", STANDBY: "stop"})
    last_damper_cmd: dict[str, str] = field(default_factory=lambda: {PRIMARY: "close", STANDBY: "close"})
    seq: int = 0

    def running(self) -> bool:
        return self.mode == MODE_RUNNING and bool(self.active_role)

    def as_dict(self) -> dict[str, object]:
        return {
            "mode": self.mode,
            "running": self.running(),
            "preferred_role": self.preferred_role,
            "active_role": self.active_role,
            "safe_reason": self.safe_reason,
            "smoke": self.smoke,
            "smoke_zone": self.smoke_zone,
            "switch": None if self.switch is None else self.switch.as_dict(),
            "auto_switches": list(self.auto_switches),
            "last_switch_at": self.last_switch_at,
            "seq": self.seq,
        }


# --- journal events -------------------------------------------------------

@dataclass(frozen=True)
class Event:
    """One append-only ventilation event: status and audit read these rows."""

    seq: int
    at: str
    event: str
    role: str = ""
    detail: str = ""
    ref: str = ""

    def as_dict(self) -> dict[str, object]:
        return {
            "seq": self.seq,
            "at": self.at,
            "event": self.event,
            "role": self.role,
            "detail": self.detail,
            "ref": self.ref,
        }
