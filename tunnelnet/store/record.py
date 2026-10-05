"""JSON encoding and the on disk layout used by the record store."""

from __future__ import annotations

import json
import os

SUFFIX = ".json"


def record_path(root: str, kind: str, record_id: str) -> str:
    """Absolute path of one record file."""

    return os.path.join(root, kind, f"{record_id}{SUFFIX}")


def encode(value: object) -> str:
    """Render a record as stable, human readable JSON."""

    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)


def decode(text: str) -> dict[str, object] | None:
    """Parse a stored document, returning ``None`` when it is not an object."""

    try:
        payload = json.loads(text)
    except ValueError:
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def record_ids(root: str, kind: str) -> list[str]:
    """Sorted identifiers of every record stored under ``kind``."""

    directory = os.path.join(root, kind)
    try:
        names = os.listdir(directory)
    except FileNotFoundError:
        return []
    ids = [name[: -len(SUFFIX)] for name in names if name.endswith(SUFFIX)]
    return sorted(ids)


def kind_names(root: str) -> list[str]:
    """Sorted record kinds present in the store root."""

    try:
        entries = os.listdir(root)
    except FileNotFoundError:
        return []
    return sorted(name for name in entries if not name.startswith("."))
