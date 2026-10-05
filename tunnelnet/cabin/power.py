"""Per cabin power baselines used by the energy quota service."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PowerBaseline:
    """The allocated watts for one cabin."""

    cabin_id: str
    watts: float

    def as_dict(self) -> dict[str, object]:
        return {"cabin_id": self.cabin_id, "watts": self.watts}


class PowerBook:
    """Holds the allocated power for every cabin."""

    def __init__(self) -> None:
        self._baselines: dict[str, float] = {}

    def set_baseline(self, cabin_id: str, watts: float) -> None:
        self._baselines[cabin_id] = watts

    def baseline(self, cabin_id: str) -> float:
        return self._baselines.get(cabin_id, 0.0)

    def total(self) -> float:
        return sum(self._baselines.values())

    def cabins(self) -> list[str]:
        return sorted(self._baselines)

    def describe(self) -> str:
        return f"power baselines={len(self._baselines)} total={self.total():.4f}"
