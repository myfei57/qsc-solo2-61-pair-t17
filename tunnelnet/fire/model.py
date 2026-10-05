"""Fire detectors and the dampers they close."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Detector:
    """One smoke detector bound to a zone."""

    id: str
    zone: str

    def as_dict(self) -> dict[str, str]:
        return {"id": self.id, "zone": self.zone}


@dataclass(frozen=True)
class DamperState:
    """Whether the fire damper of a zone is closed."""

    zone: str
    closed: bool

    def as_dict(self) -> dict[str, object]:
        return {"zone": self.zone, "closed": self.closed}
