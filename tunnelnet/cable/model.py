"""Cable records tracked by the registry."""

from __future__ import annotations

from dataclasses import dataclass

OVER_TEMPERATURE = 75.0


@dataclass
class Cable:
    """One monitored cable section."""

    id: str
    cabin: str = ""
    temp: float = 0.0
    status: str = "normal"


def status_for(temp: float) -> str:
    """Classify a temperature against the over temperature limit."""

    return "over" if temp >= OVER_TEMPERATURE else "normal"
