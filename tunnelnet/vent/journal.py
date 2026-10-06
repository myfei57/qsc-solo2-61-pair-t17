"""Durable journal that makes ventilation state and its audit one document set.

The ventilation service writes through exactly one place: every state change is
appended as an event and the current snapshot is replaced atomically in the
same shared :class:`~tunnelnet.store.Store`. The console's ventilation status
view and its ventilation audit view are therefore both projections of the same
records -- neither keeps a private in-memory copy that could disagree.
"""

from __future__ import annotations

import tempfile
import threading
import uuid
from dataclasses import dataclass

from tunnelnet.drain.retry import utc_now
from tunnelnet.store import Store

STATE_KIND = "vent_state"
STATE_ID = "bank"
EVENT_KIND = "vent_event"


@dataclass(frozen=True)
class VentEvent:
    """One durable state transition in the order it happened."""

    id: str
    event: str
    at: str
    role: str = ""
    detail: str = ""
    request_id: str = ""

    def as_dict(self) -> dict[str, str]:
        return {
            "id": self.id,
            "event": self.event,
            "at": self.at,
            "role": self.role,
            "detail": self.detail,
            "request_id": self.request_id,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> "VentEvent":
        return cls(
            id=str(payload.get("id", "")),
            event=str(payload.get("event", "")),
            at=str(payload.get("at", "")),
            role=str(payload.get("role", "")),
            detail=str(payload.get("detail", "")),
            request_id=str(payload.get("request_id", "")),
        )


class VentJournal:
    """Atomic snapshot plus append only event log on top of a store."""

    def __init__(self, store: Store, clock=utc_now) -> None:
        self._store = store
        self._clock = clock
        self._lock = threading.RLock()

    @classmethod
    def memory(cls) -> "VentJournal":
        """A journal on a throwaway directory, for tests and stand alone use."""

        return cls(Store.open(tempfile.mkdtemp(prefix="vent-")))

    def append(self, event: str, role: str = "", detail: str = "", request_id: str = "") -> VentEvent:
        entry = VentEvent(
            id=uuid.uuid4().hex,
            event=event,
            at=self._clock(),
            role=role,
            detail=detail,
            request_id=request_id,
        )
        with self._lock:
            self._store.save(EVENT_KIND, entry.id, entry.as_dict())
        return entry

    def save_snapshot(self, snapshot: dict[str, object]) -> None:
        with self._lock:
            self._store.save(STATE_KIND, STATE_ID, snapshot)

    def load_snapshot(self) -> dict[str, object] | None:
        return self._store.load(STATE_KIND, STATE_ID)

    def events(self) -> list[VentEvent]:
        payloads = [self._store.load(EVENT_KIND, record_id) for record_id in self._store.list(EVENT_KIND)]
        entries = [VentEvent.from_dict(payload) for payload in payloads if payload is not None]
        entries.sort(key=lambda entry: (entry.at, entry.id))
        return entries

    def event_count(self) -> int:
        return self._store.count(EVENT_KIND)

    def seen_request(self, request_id: str) -> bool:
        """Whether a request id already reached a terminal switch event.

        Only completed switchovers are de-duplicating -- fault notes and safe
        latch resets carry request ids for tracing but never suppress a switch.
        """

        if not request_id:
            return False
        return any(
            entry.request_id == request_id and entry.event == "vent_switched"
            for entry in self.events()
        )
