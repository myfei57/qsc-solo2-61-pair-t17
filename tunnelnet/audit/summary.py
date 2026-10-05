"""Event counters over the audit records."""

from __future__ import annotations

from collections.abc import Iterable

from .model import Record


def count_by_event(records: Iterable[Record]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in records:
        counts[record.event] = counts.get(record.event, 0) + 1
    return counts


def summary(records: Iterable[Record]) -> dict[str, int]:
    items = list(records)
    counts = count_by_event(items)
    counts["total"] = len(items)
    return counts
