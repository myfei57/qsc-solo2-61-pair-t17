"""Read only projection of the access service."""

from __future__ import annotations

from dataclasses import dataclass

from .model import AccessRequest


@dataclass(frozen=True)
class AccessState:
    """Raised requests together with the pending and granted counters."""

    requests: list[dict[str, str]]
    pending: int
    granted: int

    def as_dict(self) -> dict[str, object]:
        return {"requests": self.requests, "pending": self.pending, "granted": self.granted}


def request_payloads(requests: list[AccessRequest]) -> list[dict[str, str]]:
    return [request.payload() for request in requests]
