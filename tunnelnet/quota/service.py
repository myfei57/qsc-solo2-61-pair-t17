"""Energy quota service bound to the cabin registry and its baselines."""

from __future__ import annotations

import threading

from tunnelnet.cabin import PowerBaseline, PowerBook, Registry

from . import usage as usage_module
from .baseline import baseline_report
from .overage import overage_for
from .report import QuotaReport


class QuotaService:
    """Tracks consumption per cabin and compares it with the allocation."""

    def __init__(self, cabins: Registry, book: PowerBook) -> None:
        self._cabins = cabins
        self._book = book
        self._lock = threading.RLock()
        self._usage: dict[str, float] = {}

    def refresh_baseline(self, watts: float) -> list[PowerBaseline]:
        """Give every active cabin the same fresh allocation."""

        for cabin in self._cabins.active():
            self._book.set_baseline(cabin.id, watts)
        return self.load_report()

    def load_report(self) -> list[PowerBaseline]:
        return baseline_report(self._cabins, self._book)

    def add_usage(self, cabin_id: str, watts: float) -> float:
        with self._lock:
            self._usage[cabin_id] = self._usage.get(cabin_id, 0.0) + watts
            return self._usage[cabin_id]

    def usage(self, cabin_id: str) -> float:
        with self._lock:
            return self._usage.get(cabin_id, 0.0)

    def total_usage(self) -> float:
        with self._lock:
            return usage_module.total(self._usage)

    def peak(self) -> float:
        with self._lock:
            return usage_module.peak(self._usage)

    def usage_by_cabin(self) -> dict[str, float]:
        with self._lock:
            return dict(self._usage)

    def ranked_cabin_ids(self) -> list[str]:
        with self._lock:
            return usage_module.rank(self._usage)

    def overage(self, cabin_id: str) -> float:
        return overage_for(self.usage(cabin_id), self._book.baseline(cabin_id))

    def allocated(self) -> float:
        return self._book.total()

    def overage_total(self) -> float:
        with self._lock:
            return sum(overage_for(value, self._book.baseline(cabin)) for cabin, value in self._usage.items())

    def forecast(self, cabin_id: str, factor: float) -> float:
        return self.usage(cabin_id) * factor

    def peak_cabin(self) -> str:
        with self._lock:
            if not self._usage:
                return ""
            return usage_module.rank(self._usage)[0]

    def report(self) -> QuotaReport:
        return QuotaReport(
            allocated=self.allocated(),
            usage_total=self.total_usage(),
            overage_total=self.overage_total(),
            peak_cabin=self.peak_cabin(),
            cabins=len(self._cabins.active()),
        )

    def describe(self) -> str:
        return (
            f"quota allocated={self.allocated():.4f} usage={self.total_usage():.4f} "
            f"overage={self.overage_total():.4f}"
        )
