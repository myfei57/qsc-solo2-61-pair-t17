"""Read only projections over the record store."""

from __future__ import annotations

from dataclasses import dataclass

from .store import Store


@dataclass(frozen=True)
class StoreState:
    """Record kinds together with the total number of documents."""

    kinds: list[str]
    records: int

    def as_dict(self) -> dict[str, object]:
        return {"kinds": self.kinds, "records": self.records}


def store_state(store: Store) -> StoreState:
    return StoreState(kinds=store.kinds(), records=store.file_count())


def describe_store(store: Store) -> str:
    return f"store kinds={len(store.kinds())} records={store.file_count()}"
