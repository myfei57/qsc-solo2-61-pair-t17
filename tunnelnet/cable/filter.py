"""Moving average filter shared with the environment alarms."""

from __future__ import annotations


class MovingAverage:
    """Averages the most recent samples so a single spike cannot trip an alarm."""

    def __init__(self, size: int) -> None:
        if size < 1:
            size = 1
        self._size = size
        self._window: list[float] = []

    def filter(self, sample: float) -> float:
        self._window.append(float(sample))
        if len(self._window) > self._size:
            self._window.pop(0)
        return sum(self._window) / len(self._window)

    def window(self) -> list[float]:
        return list(self._window)

    def size(self) -> int:
        return self._size

    def reset(self) -> None:
        self._window = []

    def describe(self) -> str:
        return f"filter size={self._size} samples={len(self._window)}"
