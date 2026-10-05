"""Mark set used to raise a fire alarm only once per event key."""

from __future__ import annotations

import threading


class MarkSet:
    """Remembers event keys that have already produced an alarm."""

    def __init__(self) -> None:
        self._marks: set[str] = set()
        self._lock = threading.RLock()

    def record(self, key: str) -> bool:
        """Return ``True`` the first time a key is seen."""

        with self._lock:
            if key in self._marks:
                return False
            self._marks.add(key)
            return True

    def has(self, key: str) -> bool:
        with self._lock:
            return key in self._marks

    def count(self) -> int:
        with self._lock:
            return len(self._marks)

    def clear(self) -> None:
        with self._lock:
            self._marks = set()

    def describe(self) -> str:
        return f"marks={len(self._marks)}"
