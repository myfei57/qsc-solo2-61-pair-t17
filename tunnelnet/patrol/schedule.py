"""Patrol progress and overdue calculations."""

from __future__ import annotations

from collections.abc import Iterable

from tunnelnet.cabin import Checkpoint

from .model import CheckIn


def visited(checks: Iterable[CheckIn]) -> set[str]:
    return {check.cabin_id for check in checks}


def progress_ratio(route_length: int, checks: Iterable[CheckIn]) -> float:
    """Fraction of route positions that have been visited."""

    if route_length <= 0:
        return 0.0
    return len(list(checks)) / route_length


def overdue_cabins(
    route: Iterable[Checkpoint],
    checks: Iterable[CheckIn],
    due: dict[str, str],
    now: str,
) -> list[str]:
    """Route cabins that are past their due time and not yet visited."""

    checked = visited(checks)
    result: list[str] = []
    for checkpoint in route:
        due_at = due.get(checkpoint.cabin_id, "")
        if not due_at or now == "":
            continue
        if checkpoint.cabin_id not in checked and due_at < now:
            result.append(checkpoint.cabin_id)
    return result
