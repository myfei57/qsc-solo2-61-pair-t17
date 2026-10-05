"""Query helpers over a list of audit records."""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from .model import Record


def filter_records(records: Iterable[Record], event: str) -> list[Record]:
    return [record for record in records if record.event == event]


def last(records: Sequence[Record], n: int) -> list[Record]:
    if n <= 0:
        return []
    return list(records[-n:])


def events(records: Iterable[Record]) -> list[str]:
    seen: list[str] = []
    for record in records:
        if record.event not in seen:
            seen.append(record.event)
    return seen


def most_recent(records: Sequence[Record]) -> Record | None:
    if not records:
        return None
    return records[-1]


def between(records: Iterable[Record], start: str, end: str) -> list[Record]:
    return [record for record in records if start <= record.at <= end]
