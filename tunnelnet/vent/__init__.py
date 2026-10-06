"""Primary/standby ventilation bank with automatic fault failover.

Policy summary (full rationale in vent/README.md):

* sticky recovery   - a repaired primary stands by; no automatic switch back
* break before make - stop/confirm/close old branch before opening/starting new
* compensating saga - a planned switch that fails rolls back; otherwise safe
* single journal    - status and audit read the same on-disk event rows
"""

from .coordinator import VentService
from .hardware import FanBay, FanFeedback, SimulatedBay
from .journal import load_events
from .model import PRIMARY, STANDBY, Event, FanState, GroupState
from .report import VentState

__all__ = [
    "PRIMARY",
    "STANDBY",
    "Event",
    "FanBay",
    "FanFeedback",
    "FanState",
    "GroupState",
    "SimulatedBay",
    "VentService",
    "VentState",
    "load_events",
]
