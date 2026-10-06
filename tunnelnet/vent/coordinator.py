"""Primary/standby ventilation coordinator.

Policy fixed in this module (see README):

* Recovery is *sticky* - when the primary is repaired it becomes the healthy
  standby and keeps standing by. There is **no automatic switch back**, so a
  marginal contact cannot make the duty fan oscillate. Returning to the
  primary is an explicit :meth:`switchback` (cooldown limited).
* Switchovers are *break before make* with interlocked dampers:
  stop old fan -> confirm stopped -> close old damper -> confirm closed ->
  open new damper -> confirm open -> start new fan -> confirm running.
  Two fans can never run together and two branch dampers can never be open
  together.
* A planned switch that fails is compensated (rolled back) to the previous
  duty fan; a fault driven switch that cannot complete, or a failed
  compensation, parks the bank in the safe state (all stopped, all closed,
  latched, alarming) until manual reset.
* Automatic failovers are rate limited; flapping past the limit is a safe
  shutdown instead of another switch.
* All state changes are appended to an on-disk journal before the status
  snapshot is replaced; status and audit read the same journal.
"""

from __future__ import annotations

import threading
import time
import uuid
from collections.abc import Callable
from typing import TYPE_CHECKING

from tunnelnet.store import ExecutionMark, mark_exists, save_mark

from .hardware import FanBay, FanFeedback, SimulatedBay
from . import journal
from .model import (
    AUTO_SWITCH_LIMIT,
    AUTO_SWITCH_WINDOW,
    DAMPER_TRAVEL,
    FAULT_DEBOUNCE,
    PRIMARY,
    ROLES,
    STANDBY,
    START_CONFIRM,
    STOP_CONFIRM,
    SWITCH_COOLDOWN,
    Event,
    FanState,
    GroupState,
    MODE_RUNNING,
    MODE_SAFE,
    MODE_SMOKE,
    MODE_STOPPED,
    MODE_SWITCHING,
    SAFE_DAMPER,
    SAFE_FLAP,
    SAFE_NO_HEALTHY,
    SAFE_ROLLBACK_FAILED,
    SAFE_SWITCH_FAILED,
    SAFE_WELDED,
    SwitchSaga,
    other_role,
)
from .report import VentState

if TYPE_CHECKING:
    from tunnelnet.store import Store

# Saga phases.
P_STOP_OLD = "stop_old"
P_CLOSE_OLD = "close_old"
P_OPEN_NEW = "open_new"
P_START_NEW = "start_new"
P_RB_OPEN = "rollback_open"
P_RB_START = "rollback_start"
P_DONE = "done"
P_ROLLED_BACK = "rolled_back"
P_FAILED = "failed"

SETTLE_LIMIT = 40  # max simulated ticks a synchronous command waits per pass


def utc_stamp() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


class VentService:
    """Coordinates two fans (primary + standby), their dampers and the journal."""

    def __init__(
        self,
        store: "Store | None" = None,
        bay: FanBay | None = None,
        clock: Callable[[], float] | None = None,
        stamp: Callable[[], str] = utc_stamp,
    ) -> None:
        self._store = store
        self._bay: FanBay = bay if bay is not None else SimulatedBay()
        default_clock = (lambda: self._bay.now) if isinstance(bay, SimulatedBay) else time.monotonic
        self._clock = clock if clock is not None else default_clock
        self._stamp = stamp
        self._lock = threading.RLock()
        self._reconciled = False
        self._memory_events: list[Event] = []

        if store is not None:
            journal.verify_or_drop(store)
        loaded = journal.load_state(store) if store is not None else None
        if loaded is not None:
            self._state, self._fans = loaded
        else:
            self._state = GroupState()
            if store is not None:
                self._state.seq = journal.latest_seq(store)
            self._fans = {role: FanState(role=role) for role in ROLES}

    # ------------------------------------------------------------------ status

    def state(self) -> VentState:
        with self._lock:
            return VentState(
                running=self._state.running(),
                mode=self._state.mode,
                active_role=self._state.active_role,
                preferred_role=self._state.preferred_role,
                safe_reason=self._state.safe_reason,
                smoke=self._state.smoke,
                smoke_zone=self._state.smoke_zone,
                switch=None if self._state.switch is None else self._state.switch.as_dict(),
                fans={role: self._fans[role].as_dict() for role in ROLES},
                auto_switch_count=len(self._state.auto_switches),
            )

    def running(self) -> bool:
        with self._lock:
            return self._state.running()

    def status(self) -> str:
        return self.state().status

    def describe(self) -> str:
        with self._lock:
            active = self._state.active_role or "none"
            return (
                f"ventilation mode={self._state.mode} active={active} "
                f"primary={'ok' if self._fans[PRIMARY].healthy() else 'fault'} "
                f"standby={'ok' if self._fans[STANDBY].healthy() else 'fault'}"
            )

    def events(self) -> list[Event]:
        """Audit trail: same journal rows the status snapshot is built from."""

        if self._store is None:
            return list(self._memory_events)
        return journal.load_events(self._store)

    # ------------------------------------------------------------------ commands

    def start(self, command_id: str = "") -> bool:
        """Start ventilation on the preferred fan, failing over once if needed."""

        with self._lock:
            if not self._dedup_open(command_id):
                return self.running()
            if self._state.mode == MODE_RUNNING:
                self._dedup_done(command_id)
                return True
            if self._state.mode == MODE_SWITCHING:
                return False
            if self._state.smoke:
                return False  # smoke latch overrides; clear_smoke + start required
            if self._state.mode == MODE_SAFE:
                return False  # reset required before restart
            candidate = self._start_candidate()
            if candidate == "":
                self._enter_safe(SAFE_NO_HEALTHY)
                self._dedup_done(command_id)
                return False
            self._begin_startup(candidate)
            self._settle()
            self._dedup_done(command_id)
            return self.running()

    def stop(self, *, smoke: bool = False, zone: str = "", command_id: str = "") -> bool:
        """Stop both fans and close both dampers.

        ``smoke=True`` latches the smoke linkage; the bank stays down until
        :meth:`clear_smoke`.
        """

        with self._lock:
            if not self._dedup_open(command_id):
                return not self.running()
            aborting = self._state.switch is not None and self._state.switch.active()
            if aborting:
                self._state.switch = None
                self._emit("switchover_aborted", detail="smoke_stop" if smoke else "operator_stop")
            self._force_all_down()
            self._state.active_role = ""
            if smoke:
                self._state.smoke = True
                self._state.smoke_zone = zone
                self._state.mode = MODE_SMOKE
                self._emit("smoke_stop", detail=zone)
            elif self._state.mode == MODE_SAFE:
                pass  # keep the safe latch and its reason
            else:
                self._state.mode = MODE_STOPPED
                self._emit("vent_stopped")
            self._persist()
            self._settle()
            self._dedup_done(command_id)
            return not self.running()

    def toggle(self) -> bool:
        with self._lock:
            if self.running():
                return self.stop()
            return self.start()

    def switch_to(self, role: str, command_id: str = "") -> bool:
        """Planned, compensating switch to ``role`` (break before make)."""

        with self._lock:
            if role not in ROLES:
                raise ValueError(f"unknown fan role {role!r}")
            if not self._dedup_open(command_id):
                return self._state.active_role == role
            if self._state.mode != MODE_RUNNING or self._state.active_role == "":
                self._dedup_done(command_id)
                return False
            if self._state.active_role == role:
                self._dedup_done(command_id)
                return True  # idempotent: already duty on that fan
            if not self._fans[role].healthy():
                self._dedup_done(command_id)
                return False
            self._begin_switch(self._state.active_role, role, automatic=False)
            self._settle()
            if self._state.mode == MODE_RUNNING and self._state.active_role == role:
                self._state.preferred_role = role
                self._persist()
            self._dedup_done(command_id)
            return self._state.active_role == role and self._state.mode == MODE_RUNNING

    def switchback(self, command_id: str = "") -> bool:
        """Explicitly return duty to the primary after it has recovered."""

        with self._lock:
            now = self._clock()
            if self._state.last_switch_at >= 0 and now - self._state.last_switch_at < SWITCH_COOLDOWN:
                return False
            return self.switch_to(PRIMARY, command_id)

    def smoke(self, zone: str = "", command_id: str = "") -> bool:
        """Fire linkage: latch smoke and force the bank down. Idempotent."""

        with self._lock:
            if self._state.smoke:
                return True  # already latched - repeating a smoke report does nothing
            return self.stop(smoke=True, zone=zone, command_id=command_id)

    def clear_smoke(self) -> bool:
        with self._lock:
            if not self._state.smoke:
                return False
            if self._state.mode == MODE_SAFE:
                self._state.smoke = False
                self._state.smoke_zone = ""
                self._persist()
                return False
            self._state.smoke = False
            self._state.smoke_zone = ""
            self._state.mode = MODE_STOPPED
            self._emit("smoke_cleared")
            self._persist()
            return True

    def reset(self) -> bool:
        """Manual reset out of the safe state; rehomes latched fan faults."""

        with self._lock:
            if self._state.mode != MODE_SAFE:
                return False
            for role in ROLES:
                self._reset_fan_latch(role)
            self._state.safe_reason = ""
            self._state.auto_switches = []
            self._state.switch = None
            self._force_all_down()
            self._state.mode = MODE_STOPPED
            self._state.active_role = ""
            self._emit("safe_reset")
            self._persist()
            self._settle()
            return True

    def reset_fault(self, role: str) -> bool:
        """Clear a latched (maintenance type) fault on one repaired fan."""

        with self._lock:
            if role not in ROLES:
                raise ValueError(f"unknown fan role {role!r}")
            fan = self._fans[role]
            if fan.fault == "" and fan.damper_fault == "":
                return False
            self._reset_fan_latch(role)
            self._emit("fan_fault_reset", role=role)
            self._settle()
            return True

    # ------------------------------------------------------------------ tick

    def tick(self) -> None:
        """One scan: refresh feedback, supervise duty, advance any switchover."""

        with self._lock:
            self._reconcile_outputs()
            for role in ROLES:
                self._refresh_fan(role)
            if self._state.mode == MODE_SWITCHING:
                self._advance_saga()
            elif self._state.mode == MODE_RUNNING:
                self._supervise_running()
            # safe / smoke / stopped: outputs already commanded down; refresh
            # above keeps latching faults (e.g. welded) visible.
            self._persist()

    # ------------------------------------------------------------ internals: FSM

    def _refresh_fan(self, role: str) -> None:
        now = self._clock()
        fan = self._fans[role]
        fb = self._bay.feedback(role)

        # Hard-wired protection inputs take precedence over every fan state.
        # Isolation and thermal are level inputs, so a stopped fan under either
        # condition is not a usable standby either; they auto-clear below once
        # the input is gone (welded is a maintenance latch and never clears on
        # its own).
        if fb.contactor_welded:
            self._latch(role, "welded", fan_state="faulted")
        elif fb.thermal and fan.fault != "welded":
            self._latch(role, "thermal", fan_state="faulted")
        elif fb.local_stop and fan.fault != "welded":
            self._latch(role, "isolated", fan_state="faulted")
        elif fan.fault in ("thermal", "isolated"):
            cleared = fan.fault
            fan.fault = ""
            fan.fan = "stopped"
            fan.run_lost_at = -1.0
            self._emit("fan_recovered", role=role, detail=cleared)
        elif fan.fan == "starting":
            if fb.run:
                fan.fan = "running"
                fan.deadline = 0
                fan.run_lost_at = -1.0
                self._emit("fan_running", role=role)
            elif now > fan.deadline > 0:
                self._latch(role, "start_failed", fan_state="faulted")
        elif fan.fan == "running":
            if not fb.run:
                if fan.run_lost_at < 0:
                    fan.run_lost_at = now
                elif now - fan.run_lost_at >= FAULT_DEBOUNCE:
                    self._latch(role, "run_lost", fan_state="faulted")
            else:
                fan.run_lost_at = -1.0
        elif fan.fan == "stopping":
            if not fb.run:
                fan.fan = "stopped"
                fan.deadline = 0
                self._emit("fan_stopped", role=role)
            elif now > fan.deadline > 0:
                self._latch(role, "welded", fan_state="faulted")

        self._refresh_damper(role, fb, now)

    def _refresh_damper(self, role: str, fb: FanFeedback, now: float) -> None:
        fan = self._fans[role]
        if fan.damper == "opening":
            if fb.damper_open:
                fan.damper = "open"
                fan.deadline = 0
                self._emit("damper_open", role=role)
            elif now > fan.deadline > 0:
                fan.damper = "open"  # parked; the latch blocks further motion
                fan.damper_fault = "open_failed"
                fan.deadline = 0
                self._emit("damper_fault", role=role, detail="open_failed")
        elif fan.damper == "closing":
            if fb.damper_closed:
                fan.damper = "closed"
                fan.deadline = 0
                self._emit("damper_closed", role=role)
            elif now > fan.deadline > 0:
                fan.damper = "closed"
                fan.damper_fault = "close_failed"
                fan.deadline = 0
                self._emit("damper_fault", role=role, detail="close_failed")

    def _latch(self, role: str, fault: str, *, fan_state: str, damper_state: str | None = None) -> None:
        fan = self._fans[role]
        if fan.fault != fault:
            fan.fault = fault
            fan.fan = fan_state
            fan.run_lost_at = -1.0
            if damper_state is not None:
                fan.damper = damper_state
            fan.deadline = 0
            self._emit("fan_fault", role=role, detail=fault)

    def _reset_fan_latch(self, role: str) -> None:
        fan = self._fans[role]
        fb = self._bay.feedback(role)
        # A still active protection input cannot be reset away.
        if fb.thermal or fb.local_stop or fb.contactor_welded:
            return
        fan.fault = ""
        fan.damper_fault = ""
        fan.run_lost_at = -1.0
        # Rehome against real feedback: command everything safe and re-confirm.
        self._issue_fan(role, "stop")
        self._issue_damper(role, "close")
        fan.fan = "stopped" if not fb.run else "stopping"
        fan.damper = "closed" if fb.damper_closed else "closing"
        now = self._clock()
        fan.deadline = now + (STOP_CONFIRM if fan.fan == "stopping" else DAMPER_TRAVEL + 1)

    # ----------------------------------------------------- internals: supervision

    def _supervise_running(self) -> None:
        active = self._state.active_role
        if not active:
            return
        fan = self._fans[active]
        if fan.fault == "welded":
            self._enter_safe(SAFE_WELDED, active)
            return
        if fan.fault != "":
            # Duty fan is dead: automatic failover, or safe state.
            standby = other_role(active)
            self._emit("duty_fault", role=active, detail=fan.fault)
            now = self._clock()
            self._state.auto_switches = [t for t in self._state.auto_switches if now - t < AUTO_SWITCH_WINDOW]
            if len(self._state.auto_switches) >= AUTO_SWITCH_LIMIT:
                self._enter_safe(SAFE_FLAP, active)
                return
            if not self._fans[standby].healthy():
                self._enter_safe(SAFE_NO_HEALTHY, active)
                return
            self._state.auto_switches.append(now)
            self._begin_switch(active, standby, automatic=True)

    # ---------------------------------------------------------- internals: sagas

    def _begin_startup(self, candidate: str) -> None:
        saga = SwitchSaga(
            id=uuid.uuid4().hex,
            from_role="",
            to_role=candidate,
            automatic=False,
            rollback_role="start",
            phase=P_OPEN_NEW,
        )
        self._state.switch = saga
        self._state.mode = MODE_SWITCHING
        self._emit("startup_begin", role=candidate)
        # Enforce the interlock invariant from the very first action: the mate
        # branch is commanded down and its damper closed before anything opens.
        mate = other_role(candidate)
        self._issue_fan(mate, "stop")
        self._issue_fan(candidate, "stop")
        self._issue_damper(mate, "close")
        mate_fan = self._fans[mate]
        if mate_fan.damper in ("opening", "open"):
            mate_fan.damper = "closing"
        self._open_branch(candidate, saga)

    def _begin_switch(self, old: str, new: str, *, automatic: bool) -> None:
        saga = SwitchSaga(
            id=uuid.uuid4().hex,
            from_role=old,
            to_role=new,
            automatic=automatic,
            rollback_role="" if automatic else old,
            phase=P_STOP_OLD,
        )
        self._state.switch = saga
        self._state.mode = MODE_SWITCHING
        self._state.active_role = ""
        self._emit("switchover_begin", role=new, detail="auto" if automatic else "planned")
        # Phase one: stop the old fan and wait for its feedback to disappear.
        self._issue_fan(old, "stop")
        old_fan = self._fans[old]
        if old_fan.fan in ("starting", "running"):
            old_fan.fan = "stopping"
        # A fan already faulted (e.g. run lost) keeps its faulted marker; the
        # saga treats the stop as confirmed from the missing run feedback.
        now = self._clock()
        old_fan.deadline = now + STOP_CONFIRM
        saga.since = now
        saga.deadline = now + STOP_CONFIRM

    def _advance_saga(self) -> None:
        saga = self._state.switch
        if saga is None or not saga.active():
            return
        now = self._clock()
        phase = saga.phase

        # Backstop: every blocking phase carries a deadline. The per-actuator
        # FSM normally latches the specific fault first; this only fires if a
        # confirmation is somehow still outstanding past the bound. Phases with
        # their own timeout handling are excluded here.
        if saga.deadline > 0 and now > saga.deadline and phase not in (P_START_NEW, P_RB_START):
            if phase == P_STOP_OLD:
                self._enter_safe(SAFE_WELDED)
            elif phase == P_RB_OPEN:
                self._enter_safe(SAFE_ROLLBACK_FAILED)
            elif phase == P_OPEN_NEW:
                self._saga_failure(saga, SAFE_DAMPER)
            elif phase == P_CLOSE_OLD:
                self._saga_failure(saga, SAFE_DAMPER)
            return

        if phase == P_STOP_OLD:
            old = self._fans[saga.from_role]
            if old.fault == "welded":
                self._enter_safe(SAFE_WELDED, saga.from_role)
            elif old.fan == "stopped" or old.fault not in ("", "welded"):
                # No run feedback anymore: safe to isolate the old branch.
                self._enter_close_old(saga)
            else:
                self._latch(saga.from_role, "welded", fan_state="faulted")
                self._enter_safe(SAFE_WELDED, saga.from_role)
            return

        if phase == P_CLOSE_OLD:
            old = self._fans[saga.from_role]
            if old.damper_fault:
                self._saga_failure(saga, SAFE_DAMPER)
            elif old.damper == "closed":
                self._enter_open_new(saga, saga.to_role)
            return

        if phase == P_OPEN_NEW:
            new = self._fans[saga.to_role]
            if new.damper_fault:
                self._saga_failure(saga, SAFE_DAMPER)
            elif new.damper == "open":
                # Both ends of the interlock are now in the right position.
                self._enter_start_new(saga)
            return

        if phase == P_START_NEW:
            new = self._fans[saga.to_role]
            if new.fan == "running":
                self._saga_success(saga)
            elif new.fault != "":
                self._start_new_failed(saga)
            elif now > saga.deadline:
                self._latch(saga.to_role, "start_failed", fan_state="faulted")
                self._start_new_failed(saga)
            return

        if phase == P_RB_OPEN:
            target = self._fans[saga.rollback_role]
            if target.damper == "open":
                self._enter_rollback_start(saga)
            elif target.damper_fault or now > saga.deadline:
                self._enter_safe(SAFE_ROLLBACK_FAILED, saga.rollback_role)
            return

        if phase == P_RB_START:
            target = self._fans[saga.rollback_role]
            if target.fan == "running":
                self._rollback_success(saga)
            elif target.fault != "" or now > saga.deadline:
                self._enter_safe(SAFE_ROLLBACK_FAILED, saga.rollback_role)
            return

    def _enter_close_old(self, saga: SwitchSaga) -> None:
        saga.phase = P_CLOSE_OLD
        self._close_branch(saga.from_role, saga)

    def _enter_open_new(self, saga: SwitchSaga, role: str) -> None:
        saga.phase = P_OPEN_NEW
        self._open_branch(role, saga)

    def _enter_start_new(self, saga: SwitchSaga) -> None:
        saga.phase = P_START_NEW
        saga.attempts += 1
        role = saga.to_role
        self._issue_fan(role, "start")
        fan = self._fans[role]
        fan.fan = "starting"
        now = self._clock()
        fan.deadline = now + START_CONFIRM
        saga.since = now
        saga.deadline = now + START_CONFIRM
        self._emit("fan_start_requested", role=role)

    def _start_new_failed(self, saga: SwitchSaga) -> None:
        # Clean the failed candidate back down before doing anything else.
        self._issue_fan(saga.to_role, "stop")
        self._fans[saga.to_role].fan = "faulted"
        if saga.rollback_role == "start":
            # Startup: one automatic attempt on the other fan, then safe state.
            mate = other_role(saga.to_role)
            if saga.attempts < 2 and self._fans[mate].healthy():
                self._emit("startup_failover", role=saga.to_role)
                saga.to_role = mate
                self._enter_open_new(saga, mate)
                return
            self._enter_safe(SAFE_NO_HEALTHY)
        elif saga.rollback_role:
            self._begin_rollback(saga)
        else:
            self._enter_safe(SAFE_SWITCH_FAILED, saga.to_role)

    def _begin_rollback(self, saga: SwitchSaga) -> None:
        # Make the failed new branch safe, then restore the previous duty fan.
        self._issue_damper(saga.to_role, "close")
        self._fans[saga.to_role].damper = "closing"
        saga.phase = P_RB_OPEN
        role = saga.rollback_role
        self._open_branch(role, saga, emit="switchover_rollback")

    def _enter_rollback_start(self, saga: SwitchSaga) -> None:
        saga.phase = P_RB_START
        role = saga.rollback_role
        self._issue_fan(role, "start")
        fan = self._fans[role]
        fan.fan = "starting"
        now = self._clock()
        fan.deadline = now + START_CONFIRM
        saga.deadline = now + START_CONFIRM

    def _saga_success(self, saga: SwitchSaga) -> None:
        self._state.active_role = saga.to_role
        self._state.last_switch_at = self._clock()
        self._state.switch = None
        self._state.mode = MODE_RUNNING
        self._emit("switchover_completed", role=saga.to_role, detail="auto" if saga.automatic else "planned")

    def _rollback_success(self, saga: SwitchSaga) -> None:
        self._state.active_role = saga.rollback_role
        self._state.switch = None
        self._state.mode = MODE_RUNNING
        self._emit("switchover_rolled_back", role=saga.rollback_role)

    def _saga_failure(self, saga: SwitchSaga, reason: str) -> None:
        if saga.rollback_role and saga.rollback_role != "start":
            self._begin_rollback(saga)
        else:
            self._enter_safe(reason, saga.to_role)

    def _finish_saga(self, phase: str) -> None:
        if self._state.switch is not None:
            self._state.switch.phase = phase
        self._state.switch = None
        if self._state.mode == MODE_SWITCHING:
            self._state.mode = MODE_STOPPED

    def _open_branch(self, role: str, saga: SwitchSaga, emit: str = "damper_open_requested") -> None:
        self._issue_damper(role, "open")
        fan = self._fans[role]
        if fan.damper != "open":
            fan.damper = "opening"
        now = self._clock()
        fan.deadline = now + DAMPER_TRAVEL + 1
        saga.since = now
        saga.deadline = fan.deadline
        self._emit(emit, role=role)

    def _close_branch(self, role: str, saga: SwitchSaga) -> None:
        self._issue_damper(role, "close")
        fan = self._fans[role]
        if fan.damper != "closed":
            fan.damper = "closing"
        now = self._clock()
        fan.deadline = now + DAMPER_TRAVEL + 1
        saga.since = now
        saga.deadline = fan.deadline
        self._emit("damper_close_requested", role=role)

    # ----------------------------------------------------------- internals: safe

    def _enter_safe(self, reason: str, role: str = "") -> None:
        self._state.switch = None
        self._state.safe_reason = reason
        self._state.active_role = ""
        self._state.mode = MODE_SAFE
        self._force_all_down()
        self._emit("safe_state", role=role, detail=reason)

    def _force_all_down(self) -> None:
        for candidate in ROLES:
            self._issue_fan(candidate, "stop")
            self._issue_damper(candidate, "close")
            fan = self._fans[candidate]
            if fan.fan in ("starting", "running"):
                fan.fan = "stopping"
            if fan.damper in ("opening", "open"):
                fan.damper = "closing"

    def _start_candidate(self) -> str:
        preferred = self._state.preferred_role
        if self._fans[preferred].healthy():
            return preferred
        mate = other_role(preferred)
        if self._fans[mate].healthy():
            return mate
        return ""

    # ----------------------------------------------------------- internals: IO

    def _issue_fan(self, role: str, command: str) -> None:
        if self._state.last_fan_cmd[role] == command:
            return
        if command == "start":
            self._bay.start(role)
        else:
            self._bay.stop(role)
        self._state.last_fan_cmd[role] = command
        self._emit("fan_command", role=role, detail=command)

    def _issue_damper(self, role: str, command: str) -> None:
        if self._state.last_damper_cmd[role] == command:
            return
        if command == "open":
            self._bay.open_damper(role)
        else:
            self._bay.close_damper(role)
        self._state.last_damper_cmd[role] = command
        self._emit("damper_command", role=role, detail=command)

    def _reconcile_outputs(self) -> None:
        """Reissue persisted outputs once after boot so hardware matches intent."""

        if self._reconciled:
            return
        self._reconciled = True
        for role in ROLES:
            fan_cmd = self._state.last_fan_cmd[role]
            damper_cmd = self._state.last_damper_cmd[role]
            if fan_cmd == "start":
                self._bay.start(role)
            else:
                self._bay.stop(role)
            if damper_cmd == "open":
                self._bay.open_damper(role)
            else:
                self._bay.close_damper(role)

    # ----------------------------------------------------------- internals: bus

    def _emit(self, event: str, role: str = "", detail: str = "", ref: str = "") -> None:
        self._state.seq += 1
        row = Event(
            seq=self._state.seq,
            at=self._stamp(),
            event=event,
            role=role,
            detail=detail,
            ref=ref,
        )
        if self._store is not None:
            journal.append_event(self._store, row)
        else:
            self._memory_events.append(row)

    def _persist(self) -> None:
        if self._store is not None:
            journal.save_state(self._store, self._state, self._fans)

    def _settle(self) -> None:
        """Drive a simulated bay until the saga settles or the bound is reached."""

        if not isinstance(self._bay, SimulatedBay):
            self.tick()
            return
        # A startup that loses its first candidate opens a second attempt, so a
        # fixed bound must cover at least one complete extra saga.
        for _ in range(SETTLE_LIMIT):
            self._bay.advance(1.0)
            self.tick()
            if self._state.mode != MODE_SWITCHING:
                return
        # Still switching: most likely a second candidate attempt is underway.
        for _ in range(SETTLE_LIMIT):
            self._bay.advance(1.0)
            self.tick()
            if self._state.mode != MODE_SWITCHING:
                return

    # Command de-duplication (idempotency across retries and restarts).

    def _mark_key(self, command_id: str) -> str:
        return f"vent-command-{command_id}"

    def _dedup_open(self, command_id: str) -> bool:
        if not command_id or self._store is None:
            return True
        return not mark_exists(self._store, self._mark_key(command_id))

    def _dedup_done(self, command_id: str) -> None:
        if command_id and self._store is not None:
            save_mark(self._store, ExecutionMark(key=self._mark_key(command_id), executed_at=self._stamp()))
