"""Thread safe registry of tunnel cabins."""

from __future__ import annotations

import threading

from .model import Cabin
from .report import CabinState, RegistryState


class Registry:
    """Owns every cabin and the operations the console performs on them."""

    def __init__(self) -> None:
        self._items: dict[str, Cabin] = {}
        self._lock = threading.RLock()

    def upsert(self, cabin: Cabin) -> None:
        if not cabin.id:
            raise ValueError("cabin id is empty")
        with self._lock:
            if cabin.revision <= 0:
                cabin.revision = 1
            self._items[cabin.id] = cabin

    def extend(self, cabin: Cabin) -> Cabin:
        """Register a new cabin and stamp the next revision number."""

        cabin.revision = self.active_count() + 1
        self.upsert(cabin)
        return cabin

    def retire(self, cabin_id: str) -> None:
        self._require(cabin_id).retired = True

    def rename(self, cabin_id: str, name: str) -> None:
        self._require(cabin_id).name = name

    def assign_zone(self, cabin_id: str, zone: str) -> None:
        self._require(cabin_id).zone = zone

    def move(self, cabin_id: str, zone: str, partition: str) -> None:
        cabin = self._require(cabin_id)
        cabin.zone = zone
        cabin.partition = partition

    def label(self, cabin_id: str, label: str) -> list[str]:
        cabin = self._require(cabin_id)
        if label and label not in cabin.labels:
            cabin.labels.append(label)
        return list(cabin.labels)

    def release_door(self, cabin_id: str) -> None:
        self._require(cabin_id).door_open = True

    def seal_door(self, cabin_id: str) -> None:
        self._require(cabin_id).door_open = False

    def door_state(self, cabin_id: str) -> bool:
        return self._require(cabin_id).door_open

    def open_valve(self, cabin_id: str) -> None:
        self._require(cabin_id).valve_open = True

    def close_valve(self, cabin_id: str) -> None:
        self._require(cabin_id).valve_open = False

    def valve_state(self, cabin_id: str) -> bool:
        return self._require(cabin_id).valve_open

    def find(self, cabin_id: str) -> CabinState | None:
        with self._lock:
            cabin = self._items.get(cabin_id)
            if cabin is None:
                return None
            return CabinState.from_cabin(cabin)

    def has(self, cabin_id: str) -> bool:
        with self._lock:
            return cabin_id in self._items

    def count(self) -> int:
        with self._lock:
            return len(self._items)

    def active_count(self) -> int:
        with self._lock:
            return sum(1 for cabin in self._items.values() if not cabin.retired)

    def active(self) -> list[CabinState]:
        return self._list(include_retired=False)

    def all(self) -> list[CabinState]:
        return self._list(include_retired=True)

    def zone_cabins(self, zone: str) -> list[CabinState]:
        with self._lock:
            return [
                CabinState.from_cabin(self._items[key])
                for key in sorted(self._items)
                if self._items[key].zone == zone and not self._items[key].retired
            ]

    def zones(self) -> list[str]:
        with self._lock:
            return sorted({cabin.zone for cabin in self._items.values() if cabin.zone})

    def state(self) -> RegistryState:
        cabins = self.all()
        return RegistryState(cabins=cabins, active=self.active_count(), total=len(cabins))

    def describe(self) -> str:
        return f"cabins total={self.count()} active={self.active_count()}"

    def _list(self, include_retired: bool) -> list[CabinState]:
        with self._lock:
            return [
                CabinState.from_cabin(self._items[key])
                for key in sorted(self._items)
                if include_retired or not self._items[key].retired
            ]

    def _require(self, cabin_id: str) -> Cabin:
        with self._lock:
            cabin = self._items.get(cabin_id)
            if cabin is None:
                raise ValueError(f"cabin {cabin_id} not found")
            return cabin
