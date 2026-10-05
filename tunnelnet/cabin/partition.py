"""Partition to cabin mapping with a revision counter."""

from __future__ import annotations

import threading


class PartitionTable:
    """Maps a partition identifier to the cabin that currently owns it.

    Every rewrite bumps a revision so the environment service can tell whether
    a cached route is still valid.
    """

    def __init__(self) -> None:
        self._mapping: dict[str, str] = {}
        self._revision = 0
        self._lock = threading.RLock()

    def repartition(self, partition_id: str, cabin_id: str) -> int:
        if not partition_id:
            raise ValueError("partition id is empty")
        if not cabin_id:
            raise ValueError("cabin id is empty")
        with self._lock:
            self._mapping[partition_id] = cabin_id
            self._revision += 1
            return self._revision

    def cabin_of(self, partition_id: str) -> str:
        with self._lock:
            return self._mapping.get(partition_id, "")

    def mapping(self) -> dict[str, str]:
        with self._lock:
            return dict(self._mapping)

    def revision(self) -> int:
        with self._lock:
            return self._revision

    def describe(self) -> str:
        return f"partitions={len(self._mapping)} revision={self._revision}"
