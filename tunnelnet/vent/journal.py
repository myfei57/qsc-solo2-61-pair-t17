"""On-disk journal: the single source of truth for ventilation state.

Both the live status view and the audit view read the same files:

* ``vent/event-NNNNNNNN.json`` - append-only, immutable event rows
* ``vent/state.json``         - the latest state snapshot, rebuilt from events

An event and the snapshot it produces are written under the store lock with an
atomic rename; the event file is fsynced before the snapshot is replaced, so a
crash can never leave a snapshot ahead of its audit trail. On startup the
snapshot is verified against the events and rebuilt if anything is missing.
"""

from __future__ import annotations

import json
import os
from typing import Any

from tunnelnet.store import Store

from .model import Event, FanState, GroupState, ROLES, SwitchSaga

KIND = "vent"
STATE_ID = "state"
EVENT_PREFIX = "event-"
SUFFIX = ".json"


def _event_id(seq: int) -> str:
    return f"{EVENT_PREFIX}{seq:08d}"


def _read_json(store: Store, record_id: str) -> dict[str, Any] | None:
    return store.load(KIND, record_id)


def _write_json(store: Store, record_id: str, value: object) -> None:
    store.save(KIND, record_id, value)


def append_event(store: Store, event: Event) -> None:
    """Append one immutable event row and fsync it before callers snapshot."""

    _write_json(store, _event_id(event.seq), event.as_dict())
    _fsync_kind_dir(store)


def _fsync_kind_dir(store: Store) -> None:
    """Best effort directory fsync so the renamed event entry survives a crash."""

    path = os.path.join(store.root, KIND)
    try:
        descriptor = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    except OSError:
        pass
    finally:
        os.close(descriptor)


def event_ids(store: Store) -> list[str]:
    return [name for name in store.list(KIND) if name.startswith(EVENT_PREFIX)]


def load_events(store: Store) -> list[Event]:
    """Every event in sequence order (filenames are zero padded)."""

    rows: list[Event] = []
    for record_id in event_ids(store):
        payload = _read_json(store, record_id)
        if not isinstance(payload, dict):
            continue
        rows.append(
            Event(
                seq=int(payload.get("seq", 0)),
                at=str(payload.get("at", "")),
                event=str(payload.get("event", "")),
                role=str(payload.get("role", "")),
                detail=str(payload.get("detail", "")),
                ref=str(payload.get("ref", "")),
            )
        )
    rows.sort(key=lambda item: item.seq)
    return rows


def latest_seq(store: Store) -> int:
    ids = event_ids(store)
    if not ids:
        return 0
    last = ids[-1]
    return int(last[len(EVENT_PREFIX) : -len(SUFFIX)])


# --- snapshot -------------------------------------------------------------

def save_state(store: Store, state: GroupState, fans: dict[str, FanState]) -> None:
    """Persist the snapshot. Call only after the corresponding events are on disk."""

    payload = {"state": state.as_dict(), "fans": {role: fans[role].as_dict() for role in ROLES}}
    _write_json(store, STATE_ID, payload)


def load_state(store: Store) -> tuple[GroupState, dict[str, FanState]] | None:
    payload = _read_json(store, STATE_ID)
    if not isinstance(payload, dict) or not isinstance(payload.get("state"), dict):
        return None
    try:
        return _decode_state(payload)
    except (KeyError, TypeError, ValueError):
        return None


def _decode_state(payload: dict[str, Any]) -> tuple[GroupState, dict[str, FanState]]:
    raw = payload["state"]
    switch_raw = raw.get("switch")
    switch = None
    if isinstance(switch_raw, dict):
        switch = SwitchSaga(
            id=str(switch_raw.get("id", "")),
            from_role=str(switch_raw.get("from", "")),
            to_role=str(switch_raw.get("to", "")),
            automatic=bool(switch_raw.get("automatic", False)),
            phase=str(switch_raw.get("phase", "stop_old")),
            since=float(switch_raw.get("since", 0.0)),
            deadline=float(switch_raw.get("deadline", 0.0)),
            attempts=int(switch_raw.get("attempts", 0)),
            rollback_role=str(switch_raw.get("rollback_role", "")),
        )
    state = GroupState(
        mode=str(raw.get("mode", "stopped")),
        preferred_role=str(raw.get("preferred_role", "primary")),
        active_role=str(raw.get("active_role", "")),
        safe_reason=str(raw.get("safe_reason", "")),
        smoke=bool(raw.get("smoke", False)),
        smoke_zone=str(raw.get("smoke_zone", "")),
        switch=switch,
        auto_switches=[float(value) for value in raw.get("auto_switches", [])],
        last_switch_at=float(raw.get("last_switch_at", -1.0)),
        last_fan_cmd={role: str(raw.get("last_fan_cmd", {}).get(role, "stop")) for role in ROLES},
        last_damper_cmd={role: str(raw.get("last_damper_cmd", {}).get(role, "close")) for role in ROLES},
        seq=int(raw.get("seq", 0)),
    )
    fans: dict[str, FanState] = {}
    for role in ROLES:
        item = payload.get("fans", {}).get(role, {})
        fans[role] = FanState(
            role=role,
            fan=str(item.get("fan", "stopped")),
            damper=str(item.get("damper", "closed")),
            fault=str(item.get("fault", "")),
            damper_fault=str(item.get("damper_fault", "")),
            since=float(item.get("since", 0.0)),
            deadline=float(item.get("deadline", 0.0)),
            run_lost_at=float(item.get("run_lost_at", -1.0)),
        )
    return state, fans


def verify_or_drop(store: Store) -> None:
    """Drop a snapshot that is missing events, so it is rebuilt on startup."""

    loaded = load_state(store)
    if loaded is None:
        return
    state, _fans = loaded
    disk_seq = latest_seq(store)
    if state.seq < disk_seq:
        # Snapshot fell behind the journal; the coordinator rebuilds from events.
        store.delete(KIND, STATE_ID)


def encode_json(value: object) -> str:
    """Stable JSON used when exporting journal rows."""

    return json.dumps(value, ensure_ascii=False, sort_keys=True)
