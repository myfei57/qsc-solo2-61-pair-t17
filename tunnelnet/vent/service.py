"""Primary/standby ventilation bank with automatic fault fail over.

Behaviour pinned by :mod:`tunnelnet.vent.policy`:

* a running fan that reports a fault is switched to the standby fan once;
* the switch is break-before-make (stop fan, close its damper, open the standby
  damper, start the standby fan), each step verified against field feedback;
* a half completed switch is compensated and the bank settles *safe* (both fans
  stopped, both dampers closed); if even the compensating actions cannot reach
  that state the bank still latches safe and waits for an operator reset -- a
  switch that could not complete must never leave fans running against each
  other;
* the same switch request repeated is a no-op (idempotent), guarded in memory
  against retries in flight and durably against retries across restarts;
* primary recovery is non-revertive: the standby keeps running until an
  operator explicitly restores the primary.

All transitions go through one durable journal, which is also the audit trail.
"""

from __future__ import annotations

import threading

from .hardware import Hardware
from .journal import VentJournal
from .policy import (
    MODE_RUNNING,
    MODE_SAFE,
    MODE_STOPPED,
    PRIMARY,
    RECOVERY_NON_REVERTIVE,
    STANDBY,
    other_role,
)
from .report import VentState


class SwitchResult:
    """Outcome of one switch over request (lightweight, immutable to callers)."""

    __slots__ = ("switched", "mode", "active_role", "reason", "request_id")

    def __init__(
        self, switched: bool, mode: str, active_role: str, reason: str = "", request_id: str = ""
    ) -> None:
        self.switched = switched
        self.mode = mode
        self.active_role = active_role
        self.reason = reason
        self.request_id = request_id

    def __repr__(self) -> str:
        return (
            f"SwitchResult(switched={self.switched}, mode={self.mode!r}, "
            f"active_role={self.active_role!r}, reason={self.reason!r})"
        )


class _StepFailed(Exception):
    """Internal: a verified switch step did not reach its commanded state."""


class VentService:
    """Two fans, two path dampers, one active role and a safe latch."""

    def __init__(self, hardware: Hardware | None = None, journal: VentJournal | None = None) -> None:
        self._hardware = hardware or Hardware()
        self._journal = journal or VentJournal.memory()
        self._lock = threading.RLock()
        self._mode = MODE_STOPPED
        self._active_role = ""
        self._switch_count = 0
        self._last_request_id = ""
        self._last_event = ""
        self._reason = ""
        self._in_flight: set[str] = set()
        self._restored = False
        self._restore()

    # ------------------------------------------------------------------ boot

    def _restore(self) -> None:
        """Hydrate the desired role from the durable snapshot, then start it.

        A bank that has never been journaled comes up on the primary fan, but
        that default is not written until the first real transition so a bare
        runtime creates no on-disk records.
        """

        snapshot = self._journal.load_snapshot()
        if snapshot is None:
            self._hardware.damper(PRIMARY).open()
            self._hardware.fan(PRIMARY).start()
            self._mode = MODE_RUNNING
            self._active_role = PRIMARY
            self._last_event = "vent_startup"
            self._reason = "primary fan online"
            return

        self._restored = True
        self._mode = str(snapshot.get("mode", MODE_STOPPED))
        self._active_role = str(snapshot.get("active_role", ""))
        self._switch_count = int(snapshot.get("switch_count", 0))
        self._last_request_id = str(snapshot.get("last_request_id", ""))
        self._last_event = "vent_restored"
        self._reason = str(snapshot.get("reason", "restored from persisted state"))
        self._journal.append("vent_restored", self._active_role, self._reason)
        if self._mode == MODE_RUNNING and self._active_role:
            self._hardware.damper(self._active_role).open()
            self._hardware.fan(self._active_role).start()

    # --------------------------------------------------------------- journal

    def _record(self, event: str, role: str, detail: str, request_id: str = "") -> None:
        self._journal.append(event, role, detail, request_id)
        self._last_event = event
        self._reason = detail
        if request_id:
            self._last_request_id = request_id
        self._persist()

    def _transition(
        self,
        mode: str,
        active_role: str,
        event: str,
        role: str,
        detail: str,
        request_id: str = "",
    ) -> None:
        self._mode = mode
        self._active_role = active_role
        self._record(event, role, detail, request_id)

    def _persist(self) -> None:
        self._journal.save_snapshot(
            {
                "mode": self._mode,
                "active_role": self._active_role,
                "switch_count": self._switch_count,
                "last_request_id": self._last_request_id,
                "last_event": self._last_event,
                "reason": self._reason,
            }
        )

    # --------------------------------------------------------------- switches

    def switch_over(
        self,
        target_role: str = STANDBY,
        request_id: str = "",
        reason: str = "operator requested switch",
    ) -> SwitchResult:
        """Make ``target_role`` the running fan, break-before-make.

        Repeating an already completed request, or asking for the role already
        active, returns the current state without touching hardware.
        """

        with self._lock:
            if self._mode == MODE_SAFE:
                return SwitchResult(False, self._mode, self._active_role, "bank latched safe; reset required", request_id)
            if request_id and request_id in self._in_flight:
                return SwitchResult(False, self._mode, self._active_role, "switch already in flight", request_id)
            if request_id and self._journal.seen_request(request_id):
                return SwitchResult(False, self._mode, self._active_role, "duplicate request ignored", request_id)
            if self._active_role == target_role and self._mode == MODE_RUNNING:
                return SwitchResult(False, self._mode, self._active_role, "target role already active", request_id)

            if request_id:
                self._in_flight.add(request_id)
            try:
                old_role = self._active_role
                self._mode = MODE_STOPPED
                completed: list[tuple[str, str]] = []
                try:
                    if old_role:
                        if not self._verified_step(lambda: self._hardware.fan(old_role).stop(), "stop", old_role):
                            raise _StepFailed(f"{old_role} fan did not stop")
                        completed.append(("fan", old_role))
                        if not self._verified_step(lambda: self._hardware.damper(old_role).close(), "close", old_role):
                            raise _StepFailed(f"{old_role} damper did not close")
                        completed.append(("damper", old_role))

                    if not self._verified_step(lambda: self._hardware.damper(target_role).open(), "open", target_role):
                        raise _StepFailed(f"{target_role} damper did not open")
                    completed.append(("damper", target_role))
                    if not self._verified_step(lambda: self._hardware.fan(target_role).start(), "start", target_role):
                        raise _StepFailed(f"{target_role} fan did not start")
                    completed.append(("fan", target_role))
                except _StepFailed as failure:
                    return self._handle_switch_failure(target_role, completed, str(failure), request_id)

                self._switch_count += 1
                self._transition(
                    MODE_RUNNING,
                    target_role,
                    "vent_switched",
                    target_role,
                    f"switched from {old_role or 'none'} to {target_role}: {reason}",
                    request_id,
                )
                return SwitchResult(True, MODE_RUNNING, target_role, reason, request_id)
            finally:
                self._in_flight.discard(request_id)

    def _verified_step(self, command, label: str, role: str) -> bool:
        ok = bool(command())
        self._journal.append(f"vent_step_{label}", role, f"{label} {'ok' if ok else 'failed'}")
        return ok

    def _handle_switch_failure(
        self,
        target_role: str,
        completed: list[tuple[str, str]],
        detail: str,
        request_id: str,
    ) -> SwitchResult:
        """Compensate the attempted steps, then settle in the safe state."""

        self._journal.append("vent_switch_failed", target_role, detail, request_id)
        self._compensate(completed)
        # No fan is allowed to restart here: the old role was faulted (that is
        # why we switched) and the target failed mid-switch. The safe state is
        # the only known-good configuration, so it becomes a latched state.
        safe = self._hardware.stop_all()
        self._last_request_id = request_id or self._last_request_id
        latch_detail = (
            f"switch to {target_role} failed, rollback {'complete' if safe else 'INCOMPLETE'}: {detail}"
        )
        self._transition(MODE_SAFE, "", "vent_safe", "", latch_detail, request_id)
        return SwitchResult(False, MODE_SAFE, "", detail, request_id)

    def _compensate(self, completed: list[tuple[str, str]]) -> None:
        """Undo every completed step in reverse order.

        Each compensation only pushes hardware back toward the safe condition
        (fan off, damper closed) -- a fan that was started gets stopped and a
        damper that was opened gets closed; the stop/close steps that already
        ran left the old side safe and need no reversal.
        """

        for kind, role in reversed(completed):
            if kind == "fan":
                self._hardware.fan(role).stop()
            elif kind == "damper":
                self._hardware.damper(role).close()
        self._journal.append("vent_switch_rolled_back", "", "compensating actions finished")

    def _enter_safe(self, detail: str, request_id: str = "") -> None:
        self._hardware.stop_all()
        self._transition(MODE_SAFE, "", "vent_safe", "", detail, request_id)

    # --------------------------------------------------------------- faults

    def report_fault(self, role: str, request_id: str = "") -> SwitchResult:
        """Mark a fan failed; the active fan failing triggers one fail over."""

        with self._lock:
            self._hardware.fan(role).set_fault(True)
            if role == self._active_role and self._mode == MODE_RUNNING:
                self._record("vent_fault", role, f"{role} fan fault detected", request_id)
                standby = other_role(role)
                if self._hardware.fan(standby).failed():
                    self._enter_safe(f"{role} faulted and {standby} already faulted", request_id)
                    return SwitchResult(False, MODE_SAFE, "", "no healthy fan left", request_id)
                rid = request_id or f"auto-failover-{role}-{self._switch_count}"
                return self.switch_over(
                    standby, request_id=rid, reason=f"automatic fail over from faulted {role}"
                )
            self._record("vent_fault", role, f"{role} fan fault reported (not active)", request_id)
            return SwitchResult(False, self._mode, self._active_role, "fault on inactive fan", request_id)

    def report_healthy(self, role: str, request_id: str = "") -> SwitchResult:
        """Clear a fan fault. Never switches back on its own (non-revertive)."""

        with self._lock:
            self._hardware.fan(role).set_fault(False)
            self._record(
                "vent_healthy",
                role,
                f"{role} fan healthy again; recovery is manual ({RECOVERY_NON_REVERTIVE})",
                request_id,
            )
            return SwitchResult(False, self._mode, self._active_role, "noted; no automatic switch back", request_id)

    def restore_primary(self, request_id: str = "") -> SwitchResult:
        """Operator action: clear the safe latch and put the primary back."""

        with self._lock:
            if self._hardware.fan(PRIMARY).failed():
                return SwitchResult(False, self._mode, self._active_role, "primary still faulted", request_id)
            if self._mode == MODE_SAFE:
                # The latch is only cleared by walking the verified sequence.
                self._mode = MODE_STOPPED
            result = self.switch_over(
                PRIMARY, request_id=request_id, reason="operator restored primary"
            )
            if result.switched:
                self._record("vent_primary_restored", PRIMARY, "primary restored by operator", request_id)
            return result

    def reset_safe(self, request_id: str = "") -> SwitchResult:
        """Clear the safe latch after the field has been made healthy."""

        with self._lock:
            if self._mode != MODE_SAFE:
                return SwitchResult(False, self._mode, self._active_role, "not latched safe", request_id)
            role = PRIMARY if not self._hardware.fan(PRIMARY).failed() else STANDBY
            if self._hardware.fan(role).failed():
                return SwitchResult(False, MODE_SAFE, "", "no healthy fan to restart", request_id)
            self._mode = MODE_STOPPED
            self._record("vent_safe_reset", role, "safe latch cleared by operator", request_id)
            return self.switch_over(role, request_id=request_id or "safe-reset", reason="restart after safe latch")

    # --------------------------------------------------- operator / fire API

    def start(self, request_id: str = "") -> bool:
        """Start the bank on the primary fan (or keep the active role going)."""

        with self._lock:
            if self._mode == MODE_SAFE:
                return False
            role = self._active_role or PRIMARY
            result = self.switch_over(role, request_id=request_id, reason="operator start")
            return result.mode == MODE_RUNNING

    def stop(self, request_id: str = "") -> bool:
        """Stop the bank and close every air path. Used by the fire linkage."""

        with self._lock:
            role = self._active_role
            self._hardware.stop_all()
            self._transition(MODE_STOPPED, "", "vent_stopped", role, "bank stopped", request_id)
            return False

    def toggle(self) -> bool:
        return self.start() if not self.running() else self.stop()

    def running(self) -> bool:
        return self._mode == MODE_RUNNING

    def status(self) -> str:
        return self._mode

    def mode(self) -> str:
        return self._mode

    def active_role(self) -> str:
        return self._active_role

    def switch_count(self) -> int:
        return self._switch_count

    def safe_latched(self) -> bool:
        return self._mode == MODE_SAFE

    # --------------------------------------------------------------- views

    def state(self) -> VentState:
        return VentState(
            mode=self._mode,
            active_role=self._active_role,
            primary=self._hardware.fan(PRIMARY).snapshot(),
            standby=self._hardware.fan(STANDBY).snapshot(),
            dampers=(
                self._hardware.damper(PRIMARY).snapshot(),
                self._hardware.damper(STANDBY).snapshot(),
            ),
            switch_count=self._switch_count,
            last_request_id=self._last_request_id,
            last_event=self._last_event,
            reason=self._reason,
        )

    def events(self) -> list:
        """The durable audit trail -- the same records the status derives from."""

        return self._journal.events()

    def event_count(self) -> int:
        return self._journal.event_count()

    def describe(self) -> str:
        return (
            f"ventilation status={self._mode} active={self._active_role or 'none'} "
            f"switches={self._switch_count}"
        )
