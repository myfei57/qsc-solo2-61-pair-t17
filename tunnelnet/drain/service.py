"""Drain controller: valve first, then pump, with retry protection."""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Protocol

from tunnelnet.store import Store

from . import analysis
from .model import DrainCycle, Pit
from .report import DrainState, PitState, pit_state
from .retry import CommandGuard

DEFAULT_THRESHOLD = 0.5


class ValveController(Protocol):
    """Opens the inlet valve of a cabin before the pump starts."""

    def open_valve(self, cabin_id: str) -> None:  # pragma: no cover - structural
        ...


class PumpController(Protocol):
    """Starts the drain pump once the valve is open."""

    def start(self) -> None:  # pragma: no cover - structural
        ...


class DrainService:
    """Sequences sump drainage and de-duplicates repeated commands."""

    def __init__(self, valve: ValveController, pump: PumpController, store: Store) -> None:
        self._valve = valve
        self._pump = pump
        self._guard = CommandGuard(store)
        self._lock = threading.RLock()
        self._pits: dict[str, Pit] = {}
        self._cycles: list[DrainCycle] = []
        self._threshold = DEFAULT_THRESHOLD
        self._state = "idle"
        self._runs = 0

    def add_pit(self, pit: Pit) -> Pit:
        with self._lock:
            self._pits[pit.id] = pit
            return pit

    def set_level(self, pit_id: str, level: float) -> bool:
        with self._lock:
            pit = self._pits.get(pit_id)
            if pit is None:
                return False
            pit.water_level = level
            return True

    def level(self, pit_id: str) -> tuple[float, bool]:
        with self._lock:
            pit = self._pits.get(pit_id)
            if pit is None:
                return 0.0, False
            return pit.water_level, True

    def pits(self) -> list[PitState]:
        with self._lock:
            return [pit_state(self._pits[key]) for key in sorted(self._pits)]

    def pit_count(self) -> int:
        with self._lock:
            return len(self._pits)

    def levels(self) -> dict[str, float]:
        with self._lock:
            return {key: pit.water_level for key, pit in self._pits.items()}

    def set_levels(self, levels: dict[str, float]) -> dict[str, float]:
        for pit_id, value in levels.items():
            self.set_level(pit_id, value)
        return self.levels()

    def start_drain(self, cabin_id: str) -> None:
        """Open the cabin valve and only then start the pump."""

        self._valve.open_valve(cabin_id)
        self._state = "valve_open"
        self._pump.start()
        self._state = "pump_running"
        with self._lock:
            self._runs += 1

    def record_cycle(self, cabin_id: str, at: str) -> DrainCycle:
        cycle = DrainCycle(cabin_id=cabin_id, started_at=at)
        with self._lock:
            self._cycles.append(cycle)
            self._state = "idle"
        return cycle

    def cycles(self) -> list[DrainCycle]:
        with self._lock:
            return list(self._cycles)

    def cycle_count(self) -> int:
        with self._lock:
            return len(self._cycles)

    def set_threshold(self, value: float) -> float:
        if value < 0:
            raise ValueError("threshold must be non-negative")
        self._threshold = value
        return self._threshold

    def threshold(self) -> float:
        return self._threshold

    def is_high(self, pit_id: str) -> bool:
        level, present = self.level(pit_id)
        return present and level >= self._threshold

    def high_pits(self) -> list[PitState]:
        return [pit for pit in self.pits() if pit.water_level >= self._threshold]

    def execute(self, command_key: str, run: Callable[[], None] | None = None) -> bool:
        """Run one command unless it is in flight or already marked."""

        action = run if run is not None else (lambda: None)
        executed = self._guard.execute(command_key, action)
        if executed:
            with self._lock:
                self._runs += 1
        return executed

    def in_flight(self, command_key: str) -> bool:
        return self._guard.in_flight(command_key)

    def mark_in_flight(self, command_key: str) -> None:
        self._guard.mark_in_flight(command_key)

    def clear_in_flight(self, command_key: str) -> None:
        self._guard.clear_in_flight(command_key)

    def pending_commands(self) -> list[str]:
        return self._guard.pending()

    def run_count(self) -> int:
        with self._lock:
            return self._runs

    def set_state(self, value: str) -> str:
        self._state = value
        return self._state

    def state_name(self) -> str:
        return self._state

    def average_level(self) -> float:
        return analysis.average_level([pit.water_level for pit in self.pits()])

    def max_level(self) -> float:
        return analysis.max_level([pit.water_level for pit in self.pits()])

    def high_count(self) -> int:
        return analysis.high_count([pit.water_level for pit in self.pits()], self._threshold)

    def low_count(self) -> int:
        return analysis.low_count([pit.water_level for pit in self.pits()], self._threshold)

    def state(self) -> DrainState:
        return DrainState(
            pits=self.pits(),
            cycles=self.cycles(),
            threshold=self._threshold,
            runs=self.run_count(),
        )

    def describe(self) -> str:
        return (
            f"drain pits={self.pit_count()} cycles={self.cycle_count()} "
            f"high={self.high_count()} runs={self.run_count()}"
        )
