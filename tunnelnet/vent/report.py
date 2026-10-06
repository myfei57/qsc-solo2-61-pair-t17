"""Read only projection of the primary/standby ventilation bank."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class VentState:
    """Snapshot consumed by the console: bank mode, duty fan and both branches."""

    running: bool
    mode: str = "stopped"
    active_role: str = ""
    preferred_role: str = "primary"
    safe_reason: str = ""
    smoke: bool = False
    smoke_zone: str = ""
    switch: dict[str, object] | None = None
    fans: dict[str, dict[str, object]] | None = None
    auto_switch_count: int = 0

    @property
    def status(self) -> str:
        if self.smoke:
            return "smoke"
        if self.mode == "safe":
            return f"safe:{self.safe_reason}"
        if self.mode == "switching":
            phase = "" if self.switch is None else str(self.switch.get("phase", ""))
            return f"switching:{phase}"
        return "running" if self.running else "stopped"

    def as_dict(self) -> dict[str, object]:
        return {
            "running": self.running,
            "status": self.status,
            "mode": self.mode,
            "active_role": self.active_role,
            "preferred_role": self.preferred_role,
            "safe_reason": self.safe_reason,
            "smoke": self.smoke,
            "smoke_zone": self.smoke_zone,
            "switch": self.switch,
            "fans": self.fans or {},
            "auto_switch_count": self.auto_switch_count,
        }
