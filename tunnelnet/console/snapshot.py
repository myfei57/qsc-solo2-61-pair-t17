"""Full component snapshot exposed by the console."""

from __future__ import annotations

from typing import TYPE_CHECKING

from tunnelnet.ns import control_chain
from tunnelnet.store import store_state

if TYPE_CHECKING:  # pragma: no cover - imported only for type checkers
    from .runtime import Runtime


def collect(rt: "Runtime") -> dict[str, object]:
    """Combine every component projection into one document."""

    return {
        "chain": [step.as_dict() for step in control_chain().steps()],
        "store": store_state(rt.store).as_dict(),
        "namespaces": {"count": rt.namespaces.count(), "names": rt.namespaces.names()},
        "cabins": rt.cabins.state().as_dict(),
        "partitions": {"mapping": rt.partitions.mapping(), "revision": rt.partitions.revision()},
        "access": rt.access.state().as_dict(),
        "environment": rt.env.state().as_dict(),
        "drain": rt.drain.state().as_dict(),
        "ventilation": rt.ventilation.state().as_dict(),
        "fire": rt.fire.report().as_dict(),
        "patrol": rt.patrol.state().as_dict(),
        "quota": rt.quota.report().as_dict(),
        "cables": rt.cables.summary().as_dict(),
        "suppression": {"zones": rt.suppression.distinct_zones()},
        "audit": rt.audit.state().as_dict(),
    }
