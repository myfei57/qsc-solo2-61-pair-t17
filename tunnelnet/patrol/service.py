"""Patrol service built from the live cabin registry."""

from __future__ import annotations

import threading

from tunnelnet.cabin import Checkpoint, Registry, checkpoints

from .model import CheckIn, PatrolSummary
from .report import PatrolState
from .schedule import overdue_cabins, progress_ratio


class PatrolService:
    """Keeps the patrol route, the check-ins and the overdue set."""

    def __init__(self, cabins: Registry) -> None:
        self._cabins = cabins
        self._lock = threading.RLock()
        self._route: list[Checkpoint] = checkpoints(cabins)
        self._checks: list[CheckIn] = []
        self._due: dict[str, str] = {}

    def route(self) -> list[Checkpoint]:
        with self._lock:
            return list(self._route)

    def rebuild_route(self) -> list[Checkpoint]:
        """Rebuild the route from the cabins that are active right now."""

        with self._lock:
            self._route = checkpoints(self._cabins)
            return list(self._route)

    def check_in(self, cabin_id: str, at: str) -> CheckIn:
        check = CheckIn(cabin_id=cabin_id, at=at)
        with self._lock:
            self._checks.append(check)
        return check

    def check_ins(self) -> list[CheckIn]:
        with self._lock:
            return list(self._checks)

    def missed(self) -> list[str]:
        visited = {check.cabin_id for check in self.check_ins()}
        return [checkpoint.cabin_id for checkpoint in self.route() if checkpoint.cabin_id not in visited]

    def route_ids(self) -> list[str]:
        return [checkpoint.cabin_id for checkpoint in self.route()]

    def checked_cabin_ids(self) -> list[str]:
        return [check.cabin_id for check in self.check_ins()]

    def set_due(self, cabin_id: str, due: str) -> str:
        with self._lock:
            self._due[cabin_id] = due
            return self._due[cabin_id]

    def due(self, cabin_id: str) -> str:
        with self._lock:
            return self._due.get(cabin_id, "")

    def overdue(self, now: str) -> list[str]:
        return overdue_cabins(self.route(), self.check_ins(), dict(self._due), now)

    def progress(self) -> float:
        return progress_ratio(len(self._route), self.check_ins())

    def route_len(self) -> int:
        return len(self._route)

    def checked_count(self) -> int:
        return len(self._checks)

    def summary(self) -> PatrolSummary:
        return PatrolSummary(route=self.route_len(), checked=self.checked_count(), missed=len(self.missed()))

    def sorted_route(self) -> list[str]:
        return sorted(self.route_ids())

    def state(self) -> PatrolState:
        missed = self.missed()
        return PatrolState(
            route=self.route_ids(),
            checked=self.checked_cabin_ids(),
            missed=missed,
            progress=self.progress(),
        )

    def describe(self) -> str:
        return (
            f"patrol route={self.route_len()} checked={self.checked_count()} "
            f"missed={len(self.missed())}"
        )
