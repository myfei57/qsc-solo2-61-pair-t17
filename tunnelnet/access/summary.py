"""Counters over the raised entry requests."""

from __future__ import annotations

from collections.abc import Iterable

from .model import AccessRequest


def summarize(requests: Iterable[AccessRequest]) -> dict[str, int]:
    """Total, pending and granted request counts."""

    items = list(requests)
    return {
        "requests": len(items),
        "pending": sum(1 for request in items if request.status == "pending"),
        "granted": sum(1 for request in items if request.status == "granted"),
    }
