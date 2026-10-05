"""Patrol checkpoints derived from the live cabin registry."""

from __future__ import annotations

from dataclasses import dataclass

from .registry import Registry


@dataclass(frozen=True)
class Checkpoint:
    """One cabin position on the patrol route."""

    cabin_id: str
    order: int

    def as_dict(self) -> dict[str, object]:
        return {"cabin_id": self.cabin_id, "order": self.order}


def checkpoints(registry: Registry) -> list[Checkpoint]:
    """Order the active cabins so the patrol route follows the registry."""

    return [
        Checkpoint(cabin_id=cabin.id, order=index)
        for index, cabin in enumerate(registry.active())
    ]
