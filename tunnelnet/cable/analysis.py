"""Over temperature and load statistics for the cable registry."""

from __future__ import annotations

from .registry import CableRegistry


def danger_count(registry: CableRegistry, threshold: float) -> int:
    return sum(1 for temp in registry.temperatures() if temp >= threshold)


def healthy_count(registry: CableRegistry, threshold: float) -> int:
    return sum(1 for temp in registry.temperatures() if temp < threshold)


def load_factor(registry: CableRegistry) -> float:
    temperatures = registry.temperatures()
    if not temperatures:
        return 0.0
    return sum(temperatures) / len(temperatures)
