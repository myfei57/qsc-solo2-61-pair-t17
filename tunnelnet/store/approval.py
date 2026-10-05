"""Durable access approvals written before a cabin door is released."""

from __future__ import annotations

from dataclasses import dataclass

from .store import Store

APPROVAL_KIND = "approval"


@dataclass(frozen=True)
class Approval:
    """One granted cabin entry approval."""

    id: str
    cabin_id: str
    requester: str
    granted_at: str

    def as_dict(self) -> dict[str, str]:
        return {
            "id": self.id,
            "cabin_id": self.cabin_id,
            "requester": self.requester,
            "granted_at": self.granted_at,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> "Approval":
        return cls(
            id=str(payload.get("id", "")),
            cabin_id=str(payload.get("cabin_id", "")),
            requester=str(payload.get("requester", "")),
            granted_at=str(payload.get("granted_at", "")),
        )


def save_approval(store: Store, approval: Approval) -> None:
    """Persist an approval so a restart cannot forget the release."""

    store.save(APPROVAL_KIND, approval.id, approval.as_dict())


def load_approval(store: Store, approval_id: str) -> Approval | None:
    payload = store.load(APPROVAL_KIND, approval_id)
    if payload is None:
        return None
    return Approval.from_dict(payload)


def approval_exists(store: Store, approval_id: str) -> bool:
    return store.exists(APPROVAL_KIND, approval_id)


def list_approvals(store: Store) -> list[Approval]:
    approvals: list[Approval] = []
    for approval_id in store.list(APPROVAL_KIND):
        approval = load_approval(store, approval_id)
        if approval is not None:
            approvals.append(approval)
    return approvals


def revoke_approval(store: Store, approval_id: str) -> bool:
    return store.delete(APPROVAL_KIND, approval_id)
