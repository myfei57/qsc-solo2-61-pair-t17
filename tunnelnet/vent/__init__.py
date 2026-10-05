"""Ventilation bank that is stopped before a fire zone is linked."""

from .report import VentState
from .service import VentService

__all__ = ["VentService", "VentState"]
