"""Audit records written for every linkage event."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Record:
    """One linkage audit entry."""

    id: str
    event: str
    at: str

    def as_dict(self) -> dict[str, str]:
        return {"id": self.id, "event": self.event, "at": self.at}
