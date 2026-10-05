"""Ordered control chain and the action performed at each stage."""

from __future__ import annotations

from dataclasses import dataclass

from .stages import Stage

STAGE_ACTIONS: dict[Stage, str] = {
    Stage.ACCESS: "approve and release the cabin door",
    Stage.ENVIRONMENT: "sample the environment and route alarms",
    Stage.VENTILATION: "run the ventilation bank",
    Stage.FIRE: "link the fire zones",
    Stage.PATROL: "walk the patrol route",
    Stage.ENERGY: "meter cabin power",
    Stage.AUDIT: "record the linkage audit",
}


@dataclass(frozen=True)
class Step:
    """A stage paired with the action the operator performs there."""

    stage: Stage
    action: str

    def as_dict(self) -> dict[str, str]:
        return {"stage": self.stage.value, "action": self.action}


@dataclass(frozen=True)
class Chain:
    """An ordered collection of control stages."""

    name: str
    stages: tuple[Stage, ...]

    def index_of(self, stage: Stage) -> int:
        for index, candidate in enumerate(self.stages):
            if candidate is stage or candidate == stage:
                return index
        return -1

    def before(self, first: Stage, second: Stage) -> bool:
        first_index = self.index_of(first)
        second_index = self.index_of(second)
        return first_index >= 0 and second_index >= 0 and first_index < second_index

    def contains(self, stage: Stage) -> bool:
        return self.index_of(stage) >= 0

    def count(self) -> int:
        return len(self.stages)

    def last(self) -> Stage | None:
        if not self.stages:
            return None
        return self.stages[-1]

    def steps(self) -> list[Step]:
        return [Step(stage=stage, action=STAGE_ACTIONS.get(stage, "")) for stage in self.stages]

    def describe(self) -> str:
        return f"chain {self.name} has {len(self.stages)} stages"


def control_chain() -> Chain:
    """Return the canonical ordering of the tunnel control stages."""

    return Chain(
        name="tunnel-control",
        stages=(
            Stage.ACCESS,
            Stage.ENVIRONMENT,
            Stage.VENTILATION,
            Stage.FIRE,
            Stage.PATROL,
            Stage.ENERGY,
            Stage.AUDIT,
        ),
    )
