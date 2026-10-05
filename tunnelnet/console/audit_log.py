"""Audit entries written by console actions."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from tunnelnet.audit import Record
from tunnelnet.drain import utc_now

if TYPE_CHECKING:  # pragma: no cover - imported only for type checkers
    from .runtime import Runtime


def record_event(rt: "Runtime", event: str, ref: str = "") -> list[Record]:
    """Append an audit event and, when a reference is given, its ``_ref`` twin."""

    stamp = utc_now()
    entries = [Record(id=uuid.uuid4().hex, event=event, at=stamp)]
    if ref:
        entries.append(Record(id=uuid.uuid4().hex, event=f"{event}_ref", at=stamp))
    for entry in entries:
        rt.audit.append(entry)
    return entries
