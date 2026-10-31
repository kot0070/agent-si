"""Watcher escape guard: workspace escapes alert plus block.

Row R-321: paths are checked against the workspace root plus the stored
escape facts. A path that climbs out (``..``), that lies outside the root,
or that stored ``TAMPER_ATTEMPT`` / ``GUARD_BLOCK`` rows already flag is
refused: one ``GUARD_BLOCK`` alert row is journaled and the decision
carries ``allowed`` False. Paths inside the workspace are allowed and
write nothing. The guard never stops processes and never weakens an
existing check: it only adds the alert plus the block.
Standard library only.
"""

from __future__ import annotations

from dataclasses import dataclass

from agent_si.watcher import journal as journal_store
from agent_si.watcher.journal import ERROR_CODES, WatcherError

__all__ = (
    "ERROR_CODES",
    "WatcherError",
    "GuardDecision",
    "check_escape",
    "reset_state",
)


@dataclass(frozen=True)
class GuardDecision:
    """Escape-check outcome: allowed plus the reason."""

    allowed: bool = False
    reason: str = ""


def reset_state() -> None:
    """The guard keeps no per-run state; present for probe isolation."""
    return None


def _parts(path: str):
    """Path segments with both separators normalised."""
    return str(path).replace("\\", "/").split("/")


def _climbs(path: str) -> bool:
    """True when the path climbs out with a ``..`` segment."""
    return ".." in _parts(path)


def _inside(path: str, root: str) -> bool:
    """True when the path stays inside the workspace root."""
    if _climbs(path):
        return False
    here = str(path).replace("\\", "/")
    base = str(root).replace("\\", "/").rstrip("/")
    if here == base or here.startswith(base + "/"):
        return True
    if here.startswith("/"):
        return False
    return True


def _flagged(project_id: str, path: str) -> bool:
    """True when stored escape facts already flag this exact path."""
    for kind in ("TAMPER_ATTEMPT", "GUARD_BLOCK"):
        for row in journal_store.stored_rows(str(project_id), kind):
            if str(path) in row.refs:
                return True
    return False


def check_escape(project_id: str, path: str,
                 workspace_root: str) -> GuardDecision:
    """Allow paths inside the workspace root; alert plus block escapes.

    An escape (climbing/foreign path, or a path stored escape facts flag)
    appends one ``GUARD_BLOCK`` alert row and returns ``allowed`` False.
    """
    key = str(project_id)
    target = str(path)
    if not _inside(target, str(workspace_root)) or _flagged(key, target):
        journal_store.append_event(
            key, "watcher", "GUARD_BLOCK",
            "workspace escape blocked: %s" % target, (target,),
        )
        return GuardDecision(
            allowed=False,
            reason="workspace escape blocked: %s" % target,
        )
    return GuardDecision(allowed=True, reason="within workspace")
