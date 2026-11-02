"""FXTEAM M1: deterministic manager grouping.

The Director may wish for several Managers, but the wish alone never
decides: this module checks the wish against files and dependencies
and collapses to one Manager when the groups are not separate.
"""
from __future__ import annotations

from typing import Any

#: Hard cap from the prompt rule (max 4 Managers).
MAX_MANAGERS = 4


def _norm(path: Any) -> str:
    try:
        text = str(path or "").replace("\\", "/").strip()
    except Exception:
        return ""
    while text.startswith("./"):
        text = text[2:]
    return text


def decide_managers(
    parts: Any,
    managers: Any,
    read_only_files: Any = None,
) -> tuple[int, str, list[dict[str, Any]]]:
    """Decide how many Managers run; return (count, why, groups).

    ``parts`` is the Director parts list (part_id, files, depends_on).
    ``managers`` is the optional Director wish (manager_id, goal, parts).
    ``read_only_files`` is an optional set of shared inputs that may be
    read by several groups without forcing one Manager.
    """
    try:
        plist = list(parts or [])
    except Exception:
        plist = []
    by_id: dict[str, dict[str, Any]] = {}
    for part in plist:
        try:
            pid = str(part.get("part_id"))
        except Exception:
            continue
        if pid and pid not in by_id:
            by_id[pid] = part
    all_ids = [str(part.get("part_id")) for part in plist
               if isinstance(part, dict) and str(part.get("part_id") or "")]

    def _single(why: str) -> tuple[int, str, list[dict[str, Any]]]:
        return (1, why, [{
            "manager_id": "m1",
            "goal": "",
            "parts": list(all_ids),
        }])

    if not isinstance(managers, list) or not managers:
        return _single("one group")
    # Normalise wish (never raises).
    wish: list[dict[str, Any]] = []
    for entry in managers:
        try:
            if not isinstance(entry, dict):
                return _single("one group")
            mid = str(entry.get("manager_id") or "").strip()
            goal = str(entry.get("goal") or "")
            plist_ids = list(entry.get("parts") or [])
        except Exception:
            return _single("one group")
        if not mid:
            return _single("one group")
        if not isinstance(plist_ids, list) or not plist_ids:
            return _single("one group")
        try:
            pids = [str(item) for item in plist_ids]
        except Exception:
            return _single("one group")
        wish.append({"manager_id": mid, "goal": goal, "parts": pids})
    # Duplicate manager ids collapse to one.
    mids = [item["manager_id"] for item in wish]
    if len(set(mids)) != len(mids):
        return _single("one group")
    if len(wish) == 1:
        # Still requires exact coverage of every part once.
        only = wish[0]["parts"]
        if sorted(only) != sorted(all_ids) or len(set(only)) != len(only):
            return _single("one group")
        return (1, "one group", wish)
    if len(wish) > MAX_MANAGERS:
        return _single("too many groups, one group")
    # Every part in exactly one group.
    seen: dict[str, int] = {}
    for index, item in enumerate(wish):
        for pid in item["parts"]:
            if pid not in by_id:
                return _single("one group")
            if pid in seen:
                return _single("one group")
            seen[pid] = index
    if set(seen.keys()) != set(all_ids):
        return _single("one group")
    try:
        ro = {_norm(item) for item in (read_only_files or [])}
    except Exception:
        ro = set()
    ro.discard("")
    # File overlap across groups (read-only shared inputs excepted).
    owner: dict[str, str] = {}
    owner_group: dict[str, int] = {}
    for index, item in enumerate(wish):
        for pid in item["parts"]:
            part = by_id.get(pid) or {}
            try:
                files = list(part.get("files") or [])
            except Exception:
                files = []
            for raw in files:
                name = _norm(raw)
                if not name or name in ro:
                    continue
                if name in owner and owner_group[name] != index:
                    return _single("groups share %s" % (name,))
                if name not in owner:
                    owner[name] = pid
                    owner_group[name] = index
    # Cross-group dependency collapses to one.
    for pid, part in by_id.items():
        try:
            deps = list(part.get("depends_on") or [])
        except Exception:
            deps = []
        mine = seen.get(pid)
        for dep in deps:
            try:
                other = seen.get(str(dep))
            except Exception:
                other = None
            if other is not None and other != mine:
                return _single("groups depend on each other")
    why = "%d groups over separate files" % (len(wish),)
    return (len(wish), why, wish)
