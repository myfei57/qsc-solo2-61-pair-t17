"""Thread safe, file backed records behind the control service."""

from __future__ import annotations

import os
import threading

from . import record


class Store:
    """A directory of JSON records grouped by kind and identifier.

    Writes are atomic: each document is written to a sibling temporary file
    and then moved over the target path, so an interrupted write cannot leave
    a partial record behind.
    """

    def __init__(self, root: str) -> None:
        self._root = os.path.abspath(root)
        self._lock = threading.RLock()

    @property
    def root(self) -> str:
        return self._root

    @classmethod
    def open(cls, root: str) -> "Store":
        """Create the store directory when it is missing and return the store."""

        store = cls(root)
        os.makedirs(store._root, exist_ok=True)
        return store

    def save(self, kind: str, record_id: str, value: object) -> None:
        """Write one record, replacing any previous document atomically."""

        with self._lock:
            path = record.record_path(self._root, kind, record_id)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            temporary = f"{path}.tmp"
            with open(temporary, "w", encoding="utf-8") as handle:
                handle.write(record.encode(value))
            os.replace(temporary, path)

    def load(self, kind: str, record_id: str) -> dict[str, object] | None:
        """Read one record, or ``None`` when it is absent or unreadable."""

        with self._lock:
            try:
                with open(record.record_path(self._root, kind, record_id), encoding="utf-8") as handle:
                    return record.decode(handle.read())
            except FileNotFoundError:
                return None

    def exists(self, kind: str, record_id: str) -> bool:
        with self._lock:
            return os.path.exists(record.record_path(self._root, kind, record_id))

    def delete(self, kind: str, record_id: str) -> bool:
        """Remove one record, reporting whether it was present."""

        with self._lock:
            try:
                os.remove(record.record_path(self._root, kind, record_id))
            except FileNotFoundError:
                return False
            return True

    def list(self, kind: str) -> list[str]:
        with self._lock:
            return record.record_ids(self._root, kind)

    def count(self, kind: str) -> int:
        return len(self.list(kind))

    def kinds(self) -> list[str]:
        with self._lock:
            return record.kind_names(self._root)

    def stats(self) -> dict[str, int]:
        """Record count per kind, for the operator dashboard."""

        return {kind: self.count(kind) for kind in self.kinds()}

    def file_count(self) -> int:
        return sum(self.stats().values())

    def total_bytes(self) -> int:
        """Total size of every stored record document."""

        total = 0
        with self._lock:
            for kind in self.kinds():
                directory = os.path.join(self._root, kind)
                for name in os.listdir(directory):
                    if name.endswith(record.SUFFIX):
                        total += os.path.getsize(os.path.join(directory, name))
        return total

    def describe(self) -> str:
        return f"store kinds={len(self.kinds())} records={self.file_count()}"
