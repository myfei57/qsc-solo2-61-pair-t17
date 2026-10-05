"""Aggregate statistics over the whole record store."""

from __future__ import annotations

from dataclasses import dataclass

from .store import Store


@dataclass(frozen=True)
class StoreStats:
    """How many record kinds and documents the store currently holds."""

    kinds: int
    records: int
    bytes: int

    def as_dict(self) -> dict[str, int]:
        return {"kinds": self.kinds, "records": self.records, "bytes": self.bytes}


def summarize(store: Store) -> StoreStats:
    return StoreStats(kinds=len(store.kinds()), records=store.file_count(), bytes=store.total_bytes())
