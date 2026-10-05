"""Execution marks that make a repeated drain command a no-op."""

from __future__ import annotations

from dataclasses import dataclass

from .store import Store

MARK_KIND = "mark"


@dataclass(frozen=True)
class ExecutionMark:
    """Proof that one command key has already run to completion."""

    key: str
    executed_at: str

    def as_dict(self) -> dict[str, str]:
        return {"key": self.key, "executed_at": self.executed_at}

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> "ExecutionMark":
        return cls(key=str(payload.get("key", "")), executed_at=str(payload.get("executed_at", "")))


def save_mark(store: Store, mark: ExecutionMark) -> None:
    store.save(MARK_KIND, mark.key, mark.as_dict())


def load_mark(store: Store, key: str) -> ExecutionMark | None:
    payload = store.load(MARK_KIND, key)
    if payload is None:
        return None
    return ExecutionMark.from_dict(payload)


def mark_exists(store: Store, key: str) -> bool:
    return load_mark(store, key) is not None
