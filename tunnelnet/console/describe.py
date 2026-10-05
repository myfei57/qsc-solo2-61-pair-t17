"""Human readable component summaries."""

from __future__ import annotations

from typing import TYPE_CHECKING

from tunnelnet.ns import control_chain
from tunnelnet.store import describe_store

if TYPE_CHECKING:  # pragma: no cover - imported only for type checkers
    from .runtime import Runtime


def collect(rt: "Runtime") -> dict[str, str]:
    """Return one description line per component."""

    return {
        "chain": control_chain().describe(),
        "store": describe_store(rt.store),
        "namespaces": rt.namespaces.describe(),
        "cabins": rt.cabins.describe(),
        "partitions": rt.partitions.describe(),
        "power": rt.power_book.describe(),
        "access": rt.access.describe(),
        "environment": rt.env.describe(),
        "drain": rt.drain.describe(),
        "ventilation": rt.ventilation.describe(),
        "fire": rt.fire.describe(),
        "patrol": rt.patrol.describe(),
        "quota": rt.quota.describe(),
        "cables": rt.cables.describe(),
        "suppression": rt.suppression.describe(),
        "audit": rt.audit.describe(),
    }
