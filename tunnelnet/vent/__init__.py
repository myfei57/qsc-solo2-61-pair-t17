"""Primary/standby ventilation bank with durable fault fail over.

The bank is stopped and its dampers closed before a fire zone is linked.
Status and audit both read the same durable journal (:mod:`tunnelnet.vent.journal`).
"""

from .hardware import DamperSnapshot, DamperUnit, FanSnapshot, FanUnit, Hardware
from .journal import EVENT_KIND, STATE_KIND, VentEvent, VentJournal
from .policy import (
    PRIMARY,
    ROLES,
    STANDBY,
    MODE_RUNNING,
    MODE_SAFE,
    MODE_STOPPED,
    RECOVERY_NON_REVERTIVE,
    SEQUENCE_BREAK_BEFORE_MAKE,
    other_role,
)
from .report import VentState
from .service import SwitchResult, VentService

__all__ = [
    "DamperSnapshot",
    "DamperUnit",
    "EVENT_KIND",
    "FanSnapshot",
    "FanUnit",
    "Hardware",
    "MODE_RUNNING",
    "MODE_SAFE",
    "MODE_STOPPED",
    "PRIMARY",
    "RECOVERY_NON_REVERTIVE",
    "ROLES",
    "SEQUENCE_BREAK_BEFORE_MAKE",
    "STATE_KIND",
    "STANDBY",
    "SwitchResult",
    "VentEvent",
    "VentJournal",
    "VentService",
    "VentState",
    "other_role",
]
