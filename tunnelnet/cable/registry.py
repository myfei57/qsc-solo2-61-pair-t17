"""Thread safe registry of monitored cable sections."""

from __future__ import annotations

import threading

from .model import Cable, status_for
from .report import CableState, CableSummary, cable_state


class CableRegistry:
    """Holds cables, their temperature history and derived statistics."""

    def __init__(self) -> None:
        self._items: dict[str, Cable] = {}
        self._history: dict[str, list[float]] = {}
        self._lock = threading.RLock()

    def add(self, cable: Cable) -> Cable:
        with self._lock:
            cable.status = status_for(cable.temp)
            self._items[cable.id] = cable
            self._history.setdefault(cable.id, [])
            return cable

    def get(self, cable_id: str) -> CableState | None:
        with self._lock:
            cable = self._items.get(cable_id)
            if cable is None:
                return None
            return cable_state(cable)

    def set_temp(self, cable_id: str, temp: float) -> bool:
        with self._lock:
            cable = self._items.get(cable_id)
            if cable is None:
                return False
            cable.temp = temp
            cable.status = status_for(temp)
            return True

    def list(self) -> list[CableState]:
        with self._lock:
            return [cable_state(self._items[key]) for key in sorted(self._items)]

    def count(self) -> int:
        with self._lock:
            return len(self._items)

    def sample(self, cable_id: str, value: float) -> bool:
        with self._lock:
            if cable_id not in self._items:
                return False
            self._history.setdefault(cable_id, []).append(value)
        self.set_temp(cable_id, value)
        return True

    def history(self, cable_id: str) -> list[float]:
        with self._lock:
            return list(self._history.get(cable_id, []))

    def average(self, cable_id: str) -> float:
        values = self.history(cable_id)
        return sum(values) / len(values) if values else 0.0

    def maximum(self, cable_id: str) -> float:
        values = self.history(cable_id)
        return max(values) if values else 0.0

    def minimum(self, cable_id: str) -> float:
        values = self.history(cable_id)
        return min(values) if values else 0.0

    def over(self, cable_id: str, threshold: float) -> int:
        return sum(1 for value in self.history(cable_id) if value >= threshold)

    def sample_count(self) -> int:
        with self._lock:
            return sum(len(values) for values in self._history.values())

    def summary(self) -> CableSummary:
        return CableSummary(total=self.count(), samples=self.sample_count())

    def temperatures(self) -> list[float]:
        with self._lock:
            return [self._items[key].temp for key in sorted(self._items)]

    def describe(self) -> str:
        return f"cables total={self.count()} samples={self.sample_count()}"
