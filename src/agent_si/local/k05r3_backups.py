"""K05R3 versioned backups plus owner gate (M-D-D16).

VersionedBackupStore keeps stale knowledge copies as versioned backups;
serve_current serves the current version only and refuses a backup ref
with K05R3_BACKUP_STALE_AS_CURRENT_REFUSED, while serve_backup serves any
kept version as a read-only copy. OwnerGateBook opens one gate per owner
question and closes it only on a matching config.DecisionRecord (project
scope match plus statement bound to the gate); anything else is refused.
Standard library plus agent_si.local public imports only.
"""

from __future__ import annotations

from dataclasses import dataclass

from agent_si.local import config

#: Backup refused: a versioned backup ref asked for as current evidence.
K05R3_BACKUP_STALE_AS_CURRENT_REFUSED = "K05R3_BACKUP_STALE_AS_CURRENT_REFUSED"
#: Backup refused: unknown key or backup ref.
K05R3_BACKUP_UNKNOWN_REFUSED = "K05R3_BACKUP_UNKNOWN_REFUSED"
#: Owner gate refused: close without a matching owner decision record.
K05R3_OWNER_GATE_DECISION_REFUSED = "K05R3_OWNER_GATE_DECISION_REFUSED"
#: Owner gate refused: unknown gate, duplicate open, or close of a closed gate.
K05R3_OWNER_GATE_STATE_REFUSED = "K05R3_OWNER_GATE_STATE_REFUSED"

#: New-module error-code set (frozen ERROR_CODES_* tuples elsewhere untouched).
ERROR_CODES_K05R3_BACKUPS = (
    K05R3_BACKUP_STALE_AS_CURRENT_REFUSED,
    K05R3_BACKUP_UNKNOWN_REFUSED,
    K05R3_OWNER_GATE_DECISION_REFUSED,
    K05R3_OWNER_GATE_STATE_REFUSED,
)

#: Recipient recorded on every owner question gate.
OWNER_QUESTION_RECIPIENT = "owner"

#: Gate states; a gate opens OPEN and closes CLOSED exactly once.
GATE_OPEN = "OPEN"
GATE_CLOSED = "CLOSED"


class BackupError(Exception):
    """Backup failure; carries a K05R3_BACKUP_* code in `code`."""

    code: str

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class OwnerGateError(Exception):
    """Owner-gate failure; carries a K05R3_OWNER_GATE_* code in `code`."""

    code: str

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def backup_ref(key: str, version: int) -> str:
    """Versioned ref for one kept copy (key@vN, version 1-based)."""
    return "%s@v%d" % (key, version)


def _split_ref(ref: str) -> tuple[str, int] | None:
    """Split a backup ref back into (key, version); None when malformed."""
    if not isinstance(ref, str) or "@v" not in ref:
        return None
    key, _, tail = ref.rpartition("@v")
    if not key or not tail.isdigit():
        return None
    return (key, int(tail))


class VersionedBackupStore:
    """Stale copies kept as versioned backups; backups never serve as current."""

    def __init__(self) -> None:
        self._versions: dict[str, list[str]] = {}
        self._current: dict[str, int] = {}

    def keep(self, key: str, content: str) -> str:
        """Keep a copy under key (a repeat keep refreshes with a new version)."""
        if not isinstance(key, str) or not key:
            raise BackupError(
                K05R3_BACKUP_UNKNOWN_REFUSED,
                "backup key must be a non-empty string, got %r" % (key,),
            )
        if not isinstance(content, str):
            raise BackupError(
                K05R3_BACKUP_UNKNOWN_REFUSED,
                "backup content for key %r must be a string" % (key,),
            )
        versions = self._versions.setdefault(key, [])
        versions.append(content)
        version = len(versions)
        self._current[key] = version
        return backup_ref(key, version)

    def current_ref(self, key: str) -> str:
        """Current ref for a kept key; unknown keys are refused."""
        if key not in self._current:
            raise BackupError(
                K05R3_BACKUP_UNKNOWN_REFUSED,
                "no backup versions kept for key %r" % (key,),
            )
        return backup_ref(key, self._current[key])

    def list_versions(self, key: str) -> tuple[str, ...]:
        """Every kept version ref for a key, oldest first."""
        if key not in self._versions:
            raise BackupError(
                K05R3_BACKUP_UNKNOWN_REFUSED,
                "no backup versions kept for key %r" % (key,),
            )
        return tuple(backup_ref(key, n) for n in range(1, len(self._versions[key]) + 1))

    def serve_current(self, ref: str) -> str:
        """Serve the current copy only; a backup ref is refused as current."""
        parsed = _split_ref(ref)
        if parsed is None:
            raise BackupError(
                K05R3_BACKUP_UNKNOWN_REFUSED,
                "malformed backup ref %r" % (ref,),
            )
        key, version = parsed
        if key not in self._current:
            raise BackupError(
                K05R3_BACKUP_UNKNOWN_REFUSED,
                "no backup versions kept for key %r" % (key,),
            )
        if version != self._current[key]:
            raise BackupError(
                K05R3_BACKUP_STALE_AS_CURRENT_REFUSED,
                "backup ref %r is stale; versioned stale backup copies are "
                "never served as current" % (ref,),
            )
        return self._versions[key][version - 1]

    def serve_backup(self, ref: str) -> str:
        """Serve any kept version as a read-only backup copy."""
        parsed = _split_ref(ref)
        if parsed is None:
            raise BackupError(
                K05R3_BACKUP_UNKNOWN_REFUSED,
                "malformed backup ref %r" % (ref,),
            )
        key, version = parsed
        versions = self._versions.get(key)
        if versions is None or not 1 <= version <= len(versions):
            raise BackupError(
                K05R3_BACKUP_UNKNOWN_REFUSED,
                "no backup copy %r" % (ref,),
            )
        return versions[version - 1]


@dataclass(frozen=True)
class OwnerGate:
    """One owner question gate: OPEN until an owner decision record closes it."""

    gate_id: str
    project_key: str
    question: str
    asked_to: str = OWNER_QUESTION_RECIPIENT
    state: str = GATE_OPEN
    decided_by: str | None = None


class OwnerGateBook:
    """Owner question gates; a gate closes only on its matching decision record."""

    def __init__(self) -> None:
        self._gates: dict[str, OwnerGate] = {}

    def open_gate(self, gate_id: str, project_key: str, question: str) -> OwnerGate:
        """Open a gate carrying one owner question."""
        for name, value in (
            ("gate_id", gate_id),
            ("project_key", project_key),
            ("question", question),
        ):
            if not isinstance(value, str) or not value:
                raise OwnerGateError(
                    K05R3_OWNER_GATE_STATE_REFUSED,
                    "open_gate needs a non-empty string %s, got %r" % (name, value),
                )
        if gate_id in self._gates:
            raise OwnerGateError(
                K05R3_OWNER_GATE_STATE_REFUSED,
                "gate %r is already open" % (gate_id,),
            )
        gate = OwnerGate(gate_id=gate_id, project_key=project_key, question=question)
        self._gates[gate_id] = gate
        return gate

    def state_of(self, gate_id: str) -> OwnerGate:
        """Current gate record; unknown gates are refused."""
        try:
            return self._gates[gate_id]
        except KeyError:
            raise OwnerGateError(
                K05R3_OWNER_GATE_STATE_REFUSED,
                "unknown owner gate %r" % (gate_id,),
            ) from None

    def close_gate(
        self, gate_id: str, decision: config.DecisionRecord
    ) -> OwnerGate:
        """Close a gate on its matching owner decision record."""
        gate = self.state_of(gate_id)
        if gate.state != GATE_OPEN:
            raise OwnerGateError(
                K05R3_OWNER_GATE_STATE_REFUSED,
                "gate %r is already closed" % (gate_id,),
            )
        if not isinstance(decision, config.DecisionRecord):
            raise OwnerGateError(
                K05R3_OWNER_GATE_DECISION_REFUSED,
                "gate %r closes only on a decision record, got %r"
                % (gate_id, decision),
            )
        if decision.project_id != gate.project_key:
            raise OwnerGateError(
                K05R3_OWNER_GATE_DECISION_REFUSED,
                "decision project %r must match gate project %r"
                % (decision.project_id, gate.project_key),
            )
        if gate_id not in decision.statement:
            raise OwnerGateError(
                K05R3_OWNER_GATE_DECISION_REFUSED,
                "decision %r does not answer gate %r"
                % (decision.decision_id, gate_id),
            )
        if (
            not isinstance(decision.authority, str)
            or not decision.authority
            or decision.authority != gate.asked_to
        ):
            raise OwnerGateError(
                K05R3_OWNER_GATE_DECISION_REFUSED,
                "decision authority %r must match gate recipient %r"
                % (decision.authority, gate.asked_to),
            )
        closed = OwnerGate(
            gate_id=gate.gate_id,
            project_key=gate.project_key,
            question=gate.question,
            asked_to=gate.asked_to,
            state=GATE_CLOSED,
            decided_by=decision.decision_id,
        )
        self._gates[gate_id] = closed
        return closed
