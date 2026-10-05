"""Overage arithmetic against a cabin baseline."""

from __future__ import annotations


def overage_for(usage: float, baseline: float) -> float:
    """Watts consumed above the baseline, or zero when inside the baseline."""

    if usage <= baseline:
        return 0.0
    return usage - baseline
