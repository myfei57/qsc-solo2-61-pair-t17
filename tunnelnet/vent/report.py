"""Read only projection of the primary/standby ventilation bank."""

from __future__ import annotations

from dataclasses import dataclass

from .hardware import DamperSnapshot, FanSnapshot
from .policy import (
    MODE_RUNNING,
    MODE_SAFE,
    MODE_STOPPED,
    RECOVERY_NON_REVERTIVE,
    SEQUENCE_BREAK_BEFORE_MAKE,
)


@dataclass(frozen=True)
class VentState:
    """What the bank is doing right now and what the hardware looks like."""

    mode: str
    active_role: str
    primary: FanSnapshot
    standby: FanSnapshot
    dampers: tuple[DamperSnapshot, DamperSnapshot]
    switch_count: int = 0
    last_request_id: str = ""
    last_event: str = ""
    reason: str = ""
    recovery: str = RECOVERY_NON_REVERTIVE
    sequence: str = SEQUENCE_BREAK_BEFORE_MAKE

    @property
    def running(self) -> bool:
        return self.mode == MODE_RUNNING

    @property
    def safe(self) -> bool:
        return self.mode == MODE_SAFE

    @property
    def status(self) -> str:
        return self.mode

    @property
    def healthy(self) -> bool:
        return not (self.primary.failed and self.standby.failed)

    def as_dict(self) -> dict[str, object]:
        return {
            "running": self.running,
            "status": self.status,
            "mode": self.mode,
            "active_role": self.active_role,
            "safe": self.safe,
            "healthy": self.healthy,
            "recovery": self.recovery,
            "sequence": self.sequence,
            "switch_count": self.switch_count,
            "last_request_id": self.last_request_id,
            "last_event": self.last_event,
            "reason": self.reason,
            "fans": {
                "primary": self.primary.as_dict(),
                "standby": self.standby.as_dict(),
            },
            "dampers": [damper.as_dict() for damper in self.dampers],
        }
