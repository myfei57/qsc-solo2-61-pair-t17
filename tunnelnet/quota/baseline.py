"""Baseline projections derived from the cabin registry."""

from __future__ import annotations

from tunnelnet.cabin import PowerBaseline, PowerBook, Registry


def baseline_report(cabins: Registry, book: PowerBook) -> list[PowerBaseline]:
    """Allocated watts for every active cabin, in registry order."""

    return [PowerBaseline(cabin_id=cabin.id, watts=book.baseline(cabin.id)) for cabin in cabins.active()]
