"""Read only exports of the stored records."""

from __future__ import annotations

from .store import Store


def export_kind(store: Store, kind: str) -> dict[str, dict[str, object]]:
    """Every record of one kind, keyed by identifier."""

    records: dict[str, dict[str, object]] = {}
    for record_id in store.list(kind):
        payload = store.load(kind, record_id)
        if payload is not None:
            records[record_id] = payload
    return records


def export_all(store: Store) -> dict[str, dict[str, dict[str, object]]]:
    """Every record in the store, grouped by kind."""

    return {kind: export_kind(store, kind) for kind in store.kinds()}
