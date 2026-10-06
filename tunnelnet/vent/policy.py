"""Switch over policy for the primary/standby ventilation bank.

The two choices that behave differently while a fan contact is chattering are
pinned here so the service cannot drift between them:

``NON_REVERTIVE``
    A primary that recovers is **not** switched back to automatically. The
    standby keeps carrying the load until an operator explicitly restores the
    primary. Auto-revert would turn a flaky contact into repeated bank wide
    stop/start cycles, so it is not offered.

``BREAK_BEFORE_MAKE``
    A switch always stops the running fan and closes its path damper before the
    standby path damper opens and the standby fan starts. The two electrically
    interlocked fans can therefore never run against one another; the price is
    a short gap with no airflow.
"""

from __future__ import annotations

PRIMARY = "primary"
STANDBY = "standby"
ROLES = (PRIMARY, STANDBY)

#: Running fan is left in charge after a fault switch; recovery is manual.
RECOVERY_NON_REVERTIVE = "non_revertive"
#: Old fan is fully shut down before the new fan starts.
SEQUENCE_BREAK_BEFORE_MAKE = "break_before_make"

#: Whole bank latched safe: both fans stopped, both dampers closed.
MODE_SAFE = "safe"
#: One fan is carrying the ventilation load.
MODE_RUNNING = "running"
#: Bank is intentionally stopped, but not latched safe.
MODE_STOPPED = "stopped"


def other_role(role: str) -> str:
    """Return the peer role for ``PRIMARY``/``STANDBY``."""

    return STANDBY if role == PRIMARY else PRIMARY
