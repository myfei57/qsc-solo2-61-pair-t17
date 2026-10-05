"""Entry requests raised before a cabin door is released."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class AccessRequest:
    """One pending or granted cabin entry request."""

    id: str
    cabin_id: str
    requester: str
    status: str = "pending"

    def payload(self) -> dict[str, str]:
        return {
            "id": self.id,
            "cabin_id": self.cabin_id,
            "requester": self.requester,
            "status": self.status,
        }
