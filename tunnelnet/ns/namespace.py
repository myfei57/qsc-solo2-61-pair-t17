"""Named segments registered under the tunnel namespace."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Namespace:
    """One registered tunnel segment."""

    id: str
    name: str

    def as_dict(self) -> dict[str, str]:
        return {"id": self.id, "name": self.name}


class Registry:
    """Keeps the tunnel segments that the console can address."""

    def __init__(self) -> None:
        self._items: dict[str, Namespace] = {}

    def add(self, segment_id: str, name: str) -> Namespace:
        if not segment_id:
            raise ValueError("namespace id is empty")
        item = Namespace(id=segment_id, name=name)
        self._items[segment_id] = item
        return item

    def list(self) -> list[Namespace]:
        return [self._items[key] for key in sorted(self._items)]

    def remove(self, segment_id: str) -> bool:
        if segment_id not in self._items:
            return False
        del self._items[segment_id]
        return True

    def exists(self, segment_id: str) -> bool:
        return segment_id in self._items

    def count(self) -> int:
        return len(self._items)

    def names(self) -> list[str]:
        return sorted(self._items)

    def describe(self) -> str:
        return f"namespace segments={self.count()}"
