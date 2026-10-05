"""Command guard that keeps a repeated drain command from running twice."""

from __future__ import annotations

import time
from collections.abc import Callable

from tunnelnet.store import ExecutionMark, Store, mark_exists, save_mark


def utc_now() -> str:
    """Current UTC time in the compact form stored beside an execution mark."""

    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


class CommandGuard:
    """Suppresses a command that is already in flight or already executed."""

    def __init__(self, store: Store, clock: Callable[[], str] = utc_now) -> None:
        self._store = store
        self._clock = clock
        self._in_flight: set[str] = set()

    def in_flight(self, command_key: str) -> bool:
        return command_key in self._in_flight

    def mark_in_flight(self, command_key: str) -> None:
        self._in_flight.add(command_key)

    def clear_in_flight(self, command_key: str) -> None:
        self._in_flight.discard(command_key)

    def executed(self, command_key: str) -> bool:
        return mark_exists(self._store, command_key)

    def pending(self) -> list[str]:
        return sorted(self._in_flight)

    def execute(self, command_key: str, run: Callable[[], None]) -> bool:
        """Run a command once, returning whether it actually executed."""

        if self.in_flight(command_key) or self.executed(command_key):
            return False
        self.mark_in_flight(command_key)
        try:
            run()
        except Exception:
            self.clear_in_flight(command_key)
            raise
        save_mark(self._store, ExecutionMark(key=command_key, executed_at=self._clock()))
        self.clear_in_flight(command_key)
        return True
