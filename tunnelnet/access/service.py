"""Access service: the approval is persisted before the door is released."""

from __future__ import annotations

import threading
import time
import uuid
from typing import Protocol

from tunnelnet.store import Approval, Store, approval_exists, save_approval

from .model import AccessRequest
from .report import AccessState, request_payloads
from .summary import summarize


class DoorController(Protocol):
    """Releases the door of a cabin once an approval is durable."""

    def release_door(self, cabin_id: str) -> None:  # pragma: no cover - structural
        ...


def _stamp() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


class AccessService:
    """Submits entry requests and grants them in the durable order."""

    def __init__(self, store: Store, doors: DoorController) -> None:
        self._store = store
        self._doors = doors
        self._lock = threading.RLock()
        self._requests: list[AccessRequest] = []

    def submit(self, cabin_id: str, requester: str) -> AccessRequest:
        request = AccessRequest(id=uuid.uuid4().hex, cabin_id=cabin_id, requester=requester)
        with self._lock:
            self._requests.append(request)
        return request

    def pending(self) -> list[AccessRequest]:
        with self._lock:
            return [request for request in self._requests if request.status == "pending"]

    def approve(self, cabin_id: str, requester: str) -> Approval:
        """Persist the approval first, then release the cabin door."""

        approval = Approval(
            id=uuid.uuid4().hex,
            cabin_id=cabin_id,
            requester=requester,
            granted_at=_stamp(),
        )
        save_approval(self._store, approval)
        self._doors.release_door(cabin_id)
        return approval

    def grant(self, request_id: str) -> Approval:
        with self._lock:
            target = next((item for item in self._requests if item.id == request_id), None)
            if target is None:
                raise ValueError("request not found")
            target.status = "granted"
        return self.approve(target.cabin_id, target.requester)

    def approved(self, approval_id: str) -> bool:
        return approval_exists(self._store, approval_id)

    def request_count(self) -> int:
        with self._lock:
            return len(self._requests)

    def requests(self) -> list[AccessRequest]:
        with self._lock:
            return list(self._requests)

    def summary(self) -> dict[str, int]:
        return summarize(self.requests())

    def state(self) -> AccessState:
        summary = self.summary()
        return AccessState(
            requests=request_payloads(self.requests()),
            pending=summary["pending"],
            granted=summary["granted"],
        )

    def describe(self) -> str:
        summary = self.summary()
        return f"access requests={summary['requests']} pending={summary['pending']}"
