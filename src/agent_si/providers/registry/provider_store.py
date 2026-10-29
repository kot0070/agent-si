"""K04BIND1 provider connection persistence (ids only, never the key).

Stores the connected providers under the app store dir so a restart
re-binds them: ids, preset, model, key_ref (ids only), evidence ref,
health and the last verbatim failure reason (never secret material).
Atomic temp-file rename; corrupt or missing file reads as empty.
"""

from __future__ import annotations

import json as _json
import os as _os
from typing import Any

_FILENAME = "provider_connections.json"


def connections_path(store_dir: str) -> str:
    return _os.path.join(str(store_dir), _FILENAME)


def load_connections(store_dir: str) -> list:
    path = connections_path(store_dir)
    try:
        with open(path, "r", encoding="utf-8") as _fh:
            raw = _json.load(_fh)
    except (FileNotFoundError, NotADirectoryError):
        return []
    except (ValueError, OSError):
        return []
    if not isinstance(raw, list):
        return []
    out = []
    for item in raw:
        if isinstance(item, dict):
            out.append(dict(item))
    return out


def save_connections(store_dir: str, records: list) -> str:
    path = connections_path(store_dir)
    parent = _os.path.dirname(_os.path.abspath(path))
    if parent:
        _os.makedirs(parent, exist_ok=True)
    cleaned = []
    for item in records or []:
        if not isinstance(item, dict):
            continue
        row = {}
        for key in ("provider_id", "preset_id", "model", "instance_id",
                    "type", "base_url", "key_ref", "evidence_ref",
                    "health", "error", "mock"):
            if key in item:
                row[key] = item[key]
        # never persist key material: drop anything secret-looking
        for banned in ("key_value", "value", "secret", "api_key",
                       "apikey", "token", "password"):
            row.pop(banned, None)
        key_ref = row.get("key_ref")
        if isinstance(key_ref, dict):
            row["key_ref"] = {k: v for k, v in key_ref.items()
                              if k != "value"}
        cleaned.append(row)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as _fh:
        _fh.write(_json.dumps(cleaned, ensure_ascii=False, sort_keys=True))
    _os.replace(tmp, path)
    return path


__all__ = ["connections_path", "load_connections", "save_connections"]
