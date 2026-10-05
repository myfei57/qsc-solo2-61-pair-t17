"""Ventilation bank shared by the console and the fire linkage."""

from __future__ import annotations

from .report import VentState


class VentService:
    """A single ventilation bank that starts running."""

    def __init__(self) -> None:
        self._running = True

    def start(self) -> bool:
        self._running = True
        return self._running

    def stop(self) -> bool:
        self._running = False
        return self._running

    def running(self) -> bool:
        return self._running

    def toggle(self) -> bool:
        self._running = not self._running
        return self._running

    def status(self) -> str:
        return self.state().status

    def state(self) -> VentState:
        return VentState(running=self._running)

    def describe(self) -> str:
        return f"ventilation status={self.status()}"
