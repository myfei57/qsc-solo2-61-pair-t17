"""The pump actuator driven by the drain service."""

from __future__ import annotations


class PumpUnit:
    """Counts how many times the pump was asked to start."""

    def __init__(self) -> None:
        self._runs = 0

    def start(self) -> None:
        self._runs += 1

    def runs(self) -> int:
        return self._runs

    def describe(self) -> str:
        return f"pump runs={self._runs}"
