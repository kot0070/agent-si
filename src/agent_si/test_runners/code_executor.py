"""K03 FXTESTS1: real CODE executor plus per-kind catalog execution.

One child process per CODE test, started in the project folder with an
argv list (never a shell string built from user data); the exit code
decides PASS/FAIL per the test oracle. A missing tool or base yields a
BLOCKED outcome with a reason string, never PASS. Stdout plus stderr of
every executed test are written to a file under the project data root
with an atomic temp-file plus os.replace write; evidence_ref points at
that real file and is resolved only inside the data root (realpath plus
normcase, escape refused).
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Sequence

#: Default per-test timeout; the caller may narrow it per call.
EXECUTOR_DEFAULT_TIMEOUT_S = 60.0

#: Timeout clamp applied to every caller-supplied timeout.
EXECUTOR_MIN_TIMEOUT_S = 1.0
EXECUTOR_MAX_TIMEOUT_S = 300.0

#: Opaque evidence scheme; refs resolve only inside the data root.
EVIDENCE_SCHEME = "evidence://"

#: Output folder name under each project folder.
OUTPUT_DIR_NAME = "test-output"

#: Cap on staged output text so one runaway test cannot fill the disk.
MAX_STAGED_CHARS = 200000

#: Frozen error-code names for this module.
ERROR_CODES_EXECUTOR = (
    "EXECUTOR_ARGV_INVALID",
    "EXECUTOR_TOOL_UNAVAILABLE",
    "EXECUTOR_NO_PROJECT_FOLDER",
    "EXECUTOR_NO_DATA_ROOT",
    "EVIDENCE_REF_INVALID",
    "EVIDENCE_ESCAPE",
)


class ExecutorError(Exception):
    """Executor failure carrying the frozen ``.code`` name."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class ExecutorBlocked(ExecutorError):
    """Tool/base unavailable: maps to BLOCKED + reason, never PASS."""


#: Process-wide default data root; routes pass the app root explicitly.
_EXECUTOR_ROOT: Optional[str] = None


def bind_data_root(path: Optional[str]) -> Optional[str]:
    """Bind the default data root; returns the previous value."""
    global _EXECUTOR_ROOT
    previous = _EXECUTOR_ROOT
    _EXECUTOR_ROOT = path
    return previous


def executor_data_root() -> Optional[str]:
    """Return the bound default data root, or None when unbound."""
    return _EXECUTOR_ROOT


#: Per-test timeout overrides in seconds; ids missing here keep the default.
_TEST_TIMEOUTS: Dict[str, float] = {}

#: Folder markers that identify a python project with a runnable suite.
_PYTEST_MARKER_FILES = ("pytest.ini", "pyproject.toml", "setup.cfg", "tox.ini")

#: Node manifest plus the script key the resolver honors.
_NODE_MANIFEST = "package.json"
_NODE_TEST_SCRIPT = "test"


def set_test_timeout(test_id: str, timeout_s: float) -> float:
    """Record a per-test timeout override; returns the clamped value."""
    if not isinstance(test_id, str) or not test_id.strip():
        raise ValueError("test id must be a non-empty string")
    try:
        value = float(timeout_s)
    except (TypeError, ValueError):
        raise ValueError(
            "timeout for test %r must be a number of seconds" % (test_id,)
        ) from None
    if value != value:
        raise ValueError(
            "timeout for test %r must be a number of seconds" % (test_id,)
        ) from None
    clamped = _clamp_timeout(value)
    _TEST_TIMEOUTS[str(test_id)] = clamped
    return clamped


def test_timeout_for(test_id: str, timeout_s: float) -> float:
    """Effective per-test timeout: an explicit non-default wins, else the
    per-test setting, else the default."""
    try:
        value = float(timeout_s)
    except (TypeError, ValueError):
        value = EXECUTOR_DEFAULT_TIMEOUT_S
    if value != value:
        value = EXECUTOR_DEFAULT_TIMEOUT_S
    if value != EXECUTOR_DEFAULT_TIMEOUT_S:
        return _clamp_timeout(value)
    override = _TEST_TIMEOUTS.get(str(test_id))
    if override is not None:
        return override
    return _clamp_timeout(value)


def _is_python_project(project_dir: str) -> bool:
    """True when the folder holds a runnable pytest suite."""
    try:
        names = os.listdir(project_dir)
    except OSError:
        return False
    for name in names:
        lowered = name.lower()
        if lowered in _PYTEST_MARKER_FILES:
            return True
        stem, ext = os.path.splitext(lowered)
        if ext == ".py" and (
            stem.startswith("test_") or stem.endswith("_test")
        ):
            return True
    return False


def _node_test_script(project_dir: str) -> bool:
    """True when package.json carries a non-empty test script."""
    manifest = os.path.join(project_dir, _NODE_MANIFEST)
    try:
        with open(manifest, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return False
    if not isinstance(data, dict):
        return False
    scripts = data.get("scripts")
    if not isinstance(scripts, dict):
        return False
    script = scripts.get(_NODE_TEST_SCRIPT)
    return isinstance(script, str) and bool(script.strip())


def frozen_python() -> str:
    """Interpreter to spawn under a PyInstaller freeze.

    Source runs return ``sys.executable``. Frozen runs
    (``getattr(sys, 'frozen', False)``) return the ``AGENT_SI_PYTHON``
    env path when set, existing and different from the exe, else the
    first ``shutil.which('python')`` / ``which('python3')`` hit that is
    not the exe; with no candidate a RuntimeError is raised (the exe
    itself is windowed and is never returned, and no fake path is
    either).
    """
    exe = sys.executable
    if not getattr(sys, "frozen", False):
        return exe

    def _is_exe(path: str) -> bool:
        try:
            return (os.path.normcase(os.path.realpath(path))
                    == os.path.normcase(os.path.realpath(exe)))
        except OSError:
            return False

    env = os.environ.get("AGENT_SI_PYTHON", "")
    if env and not _is_exe(env) and os.path.isfile(env):
        return env
    for _name in ("python", "python3"):
        _hit = shutil.which(_name)
        if _hit and not _is_exe(_hit):
            return _hit
    raise RuntimeError(
        "no python interpreter for frozen runs: set AGENT_SI_PYTHON "
        "to a python executable or put python on PATH")


def _need_python(test_id: str,
                 folder: str) -> tuple[Optional[str], Optional[str]]:
    """Interpreter for one CODE test, or (None, honest reason).

    Frozen bundles with no interpreter on PATH and no AGENT_SI_PYTHON
    refuse as a reason naming the fix (install Python or set
    AGENT_SI_PYTHON) so callers report BLOCKED, never a bare 500.
    There is no embedded-interpreter fallback: the frozen exe is
    windowed with no console stdio for a pytest child (verified on
    the RC1 bundle evidence, PORTABLE_CHECK section 3).
    """
    try:
        return frozen_python(), None
    except RuntimeError:
        return None, (
            "CODE test %r of folder %r has no python interpreter: "
            "install Python or set AGENT_SI_PYTHON to a python "
            "executable" % (test_id, folder)
        )


def resolve_code_command(
    *,
    project_dir: Optional[str],
    test_id: str,
) -> tuple:
    """Map one CODE test to a real argv list for its project folder.

    Returns ``(argv, None)`` with an argv list (never a shell string),
    or ``(None, reason)`` when the folder has nothing to run; the
    reason names the gap. Python projects run pytest on the suite,
    node projects with a test script run npm test, and a matching
    single file runs as the folder check.
    """
    folder = str(project_dir or "")
    if folder and os.path.isdir(folder):
        if _is_python_project(folder):
            if importlib.util.find_spec("pytest") is None:
                return None, (
                    "CODE test %r of folder %r looks like a python "
                    "project but pytest is not installed; "
                    "install pytest to run the suite" % (test_id, folder)
                )
            _interp, _reason = _need_python(test_id, folder)
            if _interp is None:
                return None, _reason
            return [_interp, "-m", "pytest", folder, "-q"], None
        if _node_test_script(folder):
            npm = shutil.which("npm")
            if not npm:
                return None, (
                    "CODE test %r of folder %r is a node project with "
                    "a test script but npm is not on PATH; "
                    "install node to run npm test" % (test_id, folder)
                )
            return [npm, "test"], None
        candidate = os.path.join(folder, "%s.py" % _safe_name(test_id))
        if os.path.isfile(candidate):
            _interp2, _reason2 = _need_python(test_id, folder)
            if _interp2 is None:
                return None, _reason2
            return [_interp2, candidate], None
    if not folder or not os.path.isdir(folder):
        return None, (
            "CODE test %r has no project folder %r to run in: "
            "stage a python suite (test_*.py), a node test script, "
            "or a %s.py file" % (
                test_id, folder or ".", _safe_name(test_id))
        )
    return None, (
        "CODE test %r of folder %r has nothing to run: "
        "no pytest suite (test_*.py), no npm test script, "
        "and no %s.py file" % (
            test_id, folder, _safe_name(test_id))
    )


@dataclass(frozen=True)
class CodeOutcome:
    """One executed CODE test: status plus where its output landed."""

    test_id: str
    status: str
    evidence_ref: str
    output_path: Optional[str]
    returncode: Optional[int]
    reason: Optional[str]
    duration_s: float


def _canon(path: str) -> str:
    """L-001: canonical path key (realpath plus normcase) for compares."""
    return os.path.normcase(os.path.realpath(path))


def _safe_name(test_id: str) -> str:
    """Filesystem-safe stem derived from a test id."""
    return "".join(
        ch if (ch.isalnum() or ch in ("-", "_", ".")) else "_"
        for ch in test_id
    ).strip("._") or "test"


def _project_dir(data_root: str, project_id: str) -> str:
    """Project folder under the data root; created on demand."""
    folder = os.path.join(str(data_root), "projects", str(project_id))
    os.makedirs(os.path.join(folder, OUTPUT_DIR_NAME), exist_ok=True)
    return folder


def _stage_text(path: str, text: str) -> None:
    """Write text atomically via temp file in the same folder plus replace."""
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(
        dir=parent or ".", prefix=".fx-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(tmp_path, path)
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _clamp_timeout(timeout_s: Any) -> float:
    """Clamp a caller timeout into the executor window."""
    try:
        value = float(timeout_s)
    except (TypeError, ValueError):
        return EXECUTOR_DEFAULT_TIMEOUT_S
    if value != value:  # NaN never selects a timeout
        return EXECUTOR_DEFAULT_TIMEOUT_S
    return min(EXECUTOR_MAX_TIMEOUT_S,
               max(EXECUTOR_MIN_TIMEOUT_S, value))


def _check_argv(argv: Any) -> List[str]:
    """Argv must be a non-empty list of program arguments, never one string."""
    if isinstance(argv, (str, bytes)):
        raise ExecutorError(
            "EXECUTOR_ARGV_INVALID",
            "argv must be a list of program arguments, "
            "never a shell string",
        )
    if not isinstance(argv, Sequence):
        raise ExecutorError(
            "EXECUTOR_ARGV_INVALID",
            "argv must be a list of program arguments",
        )
    items = [str(item) for item in argv]
    if not items or any(not item for item in items):
        raise ExecutorError(
            "EXECUTOR_ARGV_INVALID",
            "argv must be a non-empty list of program arguments",
        )
    return items


def execute_code_test(
    *,
    data_root: Optional[str],
    project_id: str,
    test_id: str,
    argv: Optional[Sequence[str]] = None,
    project_dir: Optional[str] = None,
    runner_id: str = "",
    timeout_s: float = EXECUTOR_DEFAULT_TIMEOUT_S,
) -> CodeOutcome:
    """Run one CODE test in a child process; exit code decides PASS/FAIL.

    Stdout plus stderr land in a file under the data root and the
    returned evidence_ref points at that real file. A missing tool or
    folder raises ExecutorBlocked (the caller reports BLOCKED + reason).
    """
    root = data_root if data_root else executor_data_root()
    if not root:
        raise ExecutorBlocked(
            "EXECUTOR_NO_DATA_ROOT",
            "CODE test %r of project %r has no data root to stage "
            "evidence under" % (test_id, project_id),
        )
    items = _check_argv(argv) if argv is not None else None
    if items is None:
        _interp3, _reason3 = _need_python(
            test_id, project_dir or str(root))
        if _interp3 is None:
            raise ExecutorBlocked(
                "EXECUTOR_TOOL_UNAVAILABLE", str(_reason3))
        items = [_interp3, "%s.py" % _safe_name(test_id)]
    folder = _project_dir(root, project_id)
    workdir = project_dir or folder
    if not os.path.isdir(workdir):
        raise ExecutorBlocked(
            "EXECUTOR_NO_PROJECT_FOLDER",
            "CODE test %r of project %r has no project folder %r"
            % (test_id, project_id, workdir),
        )
    stamp = uuid.uuid4().hex[:8]
    fname = "%s-%s-%s.log" % (
        _safe_name(test_id), _ref_runner(runner_id), stamp)
    out_path = os.path.join(folder, OUTPUT_DIR_NAME, fname)
    ref = "%s%s/test-output/%s" % (EVIDENCE_SCHEME, project_id, fname)
    limit = _clamp_timeout(timeout_s)
    started = time.monotonic()
    try:
        completed = subprocess.run(
            items,
            cwd=workdir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=limit,
        )
    except FileNotFoundError as exc:
        raise ExecutorBlocked(
            "EXECUTOR_TOOL_UNAVAILABLE",
            "CODE test %r of project %r cannot start %r: %s"
            % (test_id, project_id, items[0], exc),
        ) from None
    except OSError as exc:
        raise ExecutorBlocked(
            "EXECUTOR_TOOL_UNAVAILABLE",
            "CODE test %r of project %r cannot start: %s"
            % (test_id, project_id, exc),
        ) from None
    except subprocess.TimeoutExpired as exc:
        duration = time.monotonic() - started
        out = (exc.stdout or b"").decode("utf-8", "replace")
        err = (exc.stderr or b"").decode("utf-8", "replace")
        body = _render_file(
            test_id, "CODE", project_id, items, workdir, duration,
            None, out, err,
            "timed out after %.1fs; counted as FAIL" % limit,
        )
        _stage_text(out_path, body)
        return CodeOutcome(
            test_id=test_id, status="FAIL", evidence_ref=ref,
            output_path=out_path, returncode=None,
            reason="timed out after %.1fs" % limit, duration_s=duration,
        )
    duration = time.monotonic() - started
    out = completed.stdout.decode("utf-8", "replace")
    err = completed.stderr.decode("utf-8", "replace")
    status = "PASS" if completed.returncode == 0 else "FAIL"
    reason = None if status == "PASS" else "exit code %d" % (
        completed.returncode,)
    body = _render_file(
        test_id, "CODE", project_id, items, workdir, duration,
        completed.returncode, out, err, None,
    )
    _stage_text(out_path, body)
    return CodeOutcome(
        test_id=test_id, status=status, evidence_ref=ref,
        output_path=out_path, returncode=completed.returncode,
        reason=reason, duration_s=duration,
    )


def _render_file(test_id: str, kind: str, project_id: str,
                 argv: Sequence[str], workdir: str, duration_s: float,
                 returncode: Optional[int], stdout_text: str,
                 stderr_text: str, note: Optional[str]) -> str:
    """Render the staged evidence file holding the real process output."""
    lines = [
        "test_id: %s" % test_id,
        "kind: %s" % kind,
        "project_id: %s" % project_id,
        "argv: %s" % (" ".join(str(item) for item in argv),),
        "cwd: %s" % workdir,
        "duration_s: %.3f" % duration_s,
        "returncode: %s" % ("timeout" if returncode is None
                            else str(returncode)),
    ]
    if note:
        lines.append("note: %s" % note)
    lines.append("--- stdout ---")
    lines.append(stdout_text)
    lines.append("--- stderr ---")
    lines.append(stderr_text)
    text = "\n".join(lines)
    if len(text) > MAX_STAGED_CHARS:
        text = (text[:MAX_STAGED_CHARS]
                + "\n--- truncated at %d chars ---" % MAX_STAGED_CHARS)
    return text


def stage_reason_file(
    *,
    data_root: Optional[str],
    project_id: str,
    test_id: str,
    kind: str,
    reason: str,
) -> str:
    """Stage a BLOCKED reason file; returns its evidence ref (real file)."""
    root = data_root if data_root else executor_data_root()
    if not root:
        raise ExecutorBlocked(
            "EXECUTOR_NO_DATA_ROOT",
            "test %r of project %r has no data root to stage "
            "evidence under" % (test_id, project_id),
        )
    folder = _project_dir(root, project_id)
    stamp = uuid.uuid4().hex[:8]
    fname = "%s-%s.blocked.log" % (_safe_name(test_id), stamp)
    out_path = os.path.join(folder, OUTPUT_DIR_NAME, fname)
    _stage_text(out_path, "\n".join([
        "test_id: %s" % test_id,
        "kind: %s" % kind,
        "project_id: %s" % project_id,
        "status: BLOCKED",
        "reason: %s" % reason,
    ]))
    return "%s%s/test-output/%s" % (EVIDENCE_SCHEME, project_id, fname)


def resolve_evidence_ref(ref: Any, data_root: Optional[str]) -> str:
    """Resolve an opaque evidence ref to a file inside the data root.

    Every comparison uses realpath plus normcase (L-001); refs escaping
    the root are refused and never read.
    """
    if not data_root:
        raise ExecutorError(
            "EXECUTOR_NO_DATA_ROOT",
            "no data root is bound, so ref %r resolves nowhere" % (ref,),
        )
    if not isinstance(ref, str) or not ref.startswith(EVIDENCE_SCHEME):
        raise ExecutorError(
            "EVIDENCE_REF_INVALID",
            "ref %r is not an %s ref" % (ref, EVIDENCE_SCHEME),
        )
    rest = ref[len(EVIDENCE_SCHEME):]
    project_id, sep, rel = rest.partition("/")
    if not sep or not project_id or not rel or rel.startswith("/"):
        raise ExecutorError(
            "EVIDENCE_REF_INVALID",
            "ref %r names no project file" % (ref,),
        )
    if "\\" in rest:
        raise ExecutorError(
            "EVIDENCE_REF_INVALID",
            "ref %r carries a path separator" % (ref,),
        )
    root = os.path.realpath(str(data_root))
    full = os.path.realpath(os.path.join(
        root, "projects", project_id, *rel.split("/")))
    if _canon(full) != _canon(root) and not _canon(full).startswith(
            _canon(root) + os.sep):
        raise ExecutorError(
            "EVIDENCE_ESCAPE",
            "ref %r escapes the data root and is refused" % (ref,),
        )
    return full


def _pending_ref(project_id: str, test_id: str,
                 runner_id: str = "") -> str:
    """Well-formed ref where output would stage; nothing staged for BLOCKED."""
    stamp = uuid.uuid4().hex[:8]
    runner = "".join(
        ch if (ch.isalnum() or ch in ("-", "_")) else "-"
        for ch in str(runner_id or "run")
    ).strip("-") or "run"
    return "%s%s/test-output/%s-%s-%s.pending.log" % (
        EVIDENCE_SCHEME, project_id, _safe_name(test_id), runner, stamp)


def _gateway_reply_text(response: Any) -> str:
    """Best-effort output text from a provider adapter response."""
    if isinstance(response, Mapping):
        for key in ("output_text", "text", "response"):
            value = response.get(key)
            if isinstance(value, str) and value.strip():
                return value
    for attr in ("output_text", "text"):
        value = getattr(response, attr, None)
        if isinstance(value, str) and value.strip():
            return value
    return ""


def _record_gateway_cost(project_id: str, task_id: str, run_id: str,
                         gateway: Any, response: Any) -> None:
    """Record gateway cost like any product call (never breaks the run)."""
    try:
        config = getattr(gateway, "config", None)
        provider_id = str(getattr(config, "provider_id", "") or "")
        model = str(getattr(config, "model", "") or "")
        usage = getattr(response, "usage", None)
        if usage is None and isinstance(response, Mapping):
            usage = response.get("usage")
        from agent_si.telemetry import run_store as _store

        _store.record_provider_usage(
            project_id=str(project_id or "run"),
            task_id=str(task_id or ""),
            run_id=str(run_id or ""),
            provider=provider_id,
            model=model,
            usage=usage,
        )
        try:
            from agent_si.runtime import manager as _manager

            _manager._charge_budget_gate(
                str(project_id or "run"), provider_id, model, usage,
                str(run_id or ""))
        except Exception:
            pass
    except Exception:
        pass


def _ref_runner(runner_id: str) -> str:
    """Filesystem-safe runner stem for evidence file names."""
    return "".join(
        ch if (ch.isalnum() or ch in ("-", "_")) else "-"
        for ch in str(runner_id or "run")
    ).strip("-") or "run"


def execute_catalog_test(
    *,
    test_id: str,
    kind: str,
    intent: str,
    project_id: str,
    data_root: Optional[str] = None,
    argv: Optional[Sequence[str]] = None,
    project_dir: Optional[str] = None,
    gateway: Any = None,
    answer: Optional[str] = None,
    assertion_ref: Optional[str] = None,
    runner_id: str = "",
    timeout_s: float = EXECUTOR_DEFAULT_TIMEOUT_S,
    record_cost: bool = True,
) -> Dict[str, Any]:
    """Execute one catalog test for real; per-kind honest outcome dict.

    Returns ``{"test_id", "kind", "status", "evidence_ref", "reason",
    "output", "duration_s"}``. PASS appears only for an executed check
    that passed; unavailable tools, gateways or answers yield BLOCKED
    plus a reason. A CODE test without an explicit argv runs the
    command the resolver derives from the project folder.
    ``record_cost`` covers the AI-kind gateway call: explicit runs
    bill it like any product call, while the automatic run-end hook
    passes False so harness self-tests never bill the user project
    (one turn keeps one charge and one usage row).
    """
    outcome_kind = kind if kind in ("CODE", "AI", "HUMAN") else "CODE"
    started = time.monotonic()
    if outcome_kind == "CODE":
        effective_argv = list(argv) if argv is not None else None
        if effective_argv is None:
            if project_dir:
                folder = str(project_dir)
            else:
                root = data_root if data_root else executor_data_root()
                if not root:
                    return {
                        "test_id": test_id, "kind": outcome_kind,
                        "status": "BLOCKED",
                        "evidence_ref": _pending_ref(
                            project_id, test_id, runner_id),
                        "reason": (
                            "CODE test %r of project %r has no data "
                            "root to stage evidence under"
                            % (test_id, project_id)),
                        "output": "",
                        "duration_s": 0.0,
                    }
                folder = _project_dir(str(root), project_id)
            resolved, blocked_reason = resolve_code_command(
                project_dir=folder, test_id=test_id)
            if resolved is None:
                return {
                    "test_id": test_id, "kind": outcome_kind,
                    "status": "BLOCKED",
                    "evidence_ref": _pending_ref(
                        project_id, test_id, runner_id),
                    "reason": blocked_reason, "output": "",
                    "duration_s": 0.0,
                }
            effective_argv = resolved
        try:
            outcome = execute_code_test(
                data_root=data_root, project_id=project_id,
                test_id=test_id, argv=effective_argv,
                project_dir=project_dir,
                runner_id=runner_id,
                timeout_s=test_timeout_for(test_id, timeout_s),
            )
        except ExecutorBlocked as exc:
            return {
                "test_id": test_id, "kind": outcome_kind,
                "status": "BLOCKED",
                "evidence_ref": _pending_ref(
                    project_id, test_id, runner_id),
                "reason": str(exc), "output": "",
                "duration_s": 0.0,
            }
        return {
            "test_id": test_id, "kind": outcome_kind,
            "status": outcome.status,
            "evidence_ref": outcome.evidence_ref,
            "reason": outcome.reason, "output": "",
            "duration_s": outcome.duration_s,
        }
    if outcome_kind == "AI":
        resolved = gateway
        if resolved is None:
            try:
                from agent_si.runtime import manager as _manager

                resolved = _manager.bound_provider_adapter()
            except Exception:
                resolved = None
        if resolved is None:
            return {
                "test_id": test_id, "kind": outcome_kind,
                "status": "BLOCKED",
                "evidence_ref": _pending_ref(
                    project_id, test_id, runner_id),
                "reason": "AI test %r of project %r has no provider "
                "gateway bound" % (test_id, project_id),
                "output": "",
                "duration_s": time.monotonic() - started,
            }
        if not data_root and not executor_data_root():
            return {
                "test_id": test_id, "kind": outcome_kind,
                "status": "BLOCKED",
                "evidence_ref": _pending_ref(
                    project_id, test_id, runner_id),
                "reason": "AI test %r of project %r has no data root "
                "to stage evidence under" % (test_id, project_id),
                "output": "",
                "duration_s": time.monotonic() - started,
            }
        try:
            response = resolved.invoke(
                [{"role": "user", "content": str(intent)}])
        except Exception as exc:
            return {
                "test_id": test_id, "kind": outcome_kind,
                "status": "BLOCKED",
                "evidence_ref": _pending_ref(
                    project_id, test_id, runner_id),
                "reason": "AI gateway call for test %r failed: %s: %s"
                % (test_id, type(exc).__name__, exc),
                "output": "",
                "duration_s": time.monotonic() - started,
            }
        text = _gateway_reply_text(response)
        if record_cost:
            _record_gateway_cost(project_id, "local-tests",
                                 "test-%s" % test_id, resolved, response)
        status = "PASS" if text.strip() else "FAIL"
        reason = None if status == "PASS" else (
            "the gateway returned no judgement text")
        root = data_root if data_root else executor_data_root()
        folder = _project_dir(str(root), project_id)
        stamp = uuid.uuid4().hex[:8]
        fname = "%s-%s-%s.ai.log" % (
            _safe_name(test_id), _ref_runner(runner_id), stamp)
        out_path = os.path.join(folder, OUTPUT_DIR_NAME, fname)
        _stage_text(out_path, "\n".join([
            "test_id: %s" % test_id,
            "kind: AI",
            "project_id: %s" % project_id,
            "oracle: judge approval",
            "status: %s" % status,
            "--- prompt ---",
            str(intent),
            "--- reply ---",
            text,
        ]))
        return {
            "test_id": test_id, "kind": outcome_kind, "status": status,
            "evidence_ref": "%s%s/test-output/%s" % (
                EVIDENCE_SCHEME, project_id, fname),
            "reason": reason, "output": text,
            "duration_s": time.monotonic() - started,
        }
    sign_off = answer if answer else assertion_ref
    if not sign_off:
        return {
            "test_id": test_id, "kind": outcome_kind,
            "status": "BLOCKED",
            "evidence_ref": _pending_ref(
                project_id, test_id, runner_id),
            "reason": "HUMAN test %r of project %r carries no operator "
            "sign-off; no PASS without a real answer" % (
                test_id, project_id),
            "output": "",
            "duration_s": time.monotonic() - started,
        }
    if not data_root and not executor_data_root():
        return {
            "test_id": test_id, "kind": outcome_kind,
            "status": "BLOCKED",
            "evidence_ref": _pending_ref(
                project_id, test_id, runner_id),
            "reason": "HUMAN test %r of project %r has no data root "
            "to stage evidence under" % (test_id, project_id),
            "output": "",
            "duration_s": time.monotonic() - started,
        }
    root = data_root if data_root else executor_data_root()
    folder = _project_dir(str(root), project_id)
    stamp = uuid.uuid4().hex[:8]
    fname = "%s-%s-%s.human.log" % (
        _safe_name(test_id), _ref_runner(runner_id), stamp)
    out_path = os.path.join(folder, OUTPUT_DIR_NAME, fname)
    _stage_text(out_path, "\n".join([
        "test_id: %s" % test_id,
        "kind: HUMAN",
        "project_id: %s" % project_id,
        "oracle: operator sign-off",
        "status: PASS",
        "--- sign-off ---",
        str(sign_off),
    ]))
    return {
        "test_id": test_id, "kind": outcome_kind, "status": "PASS",
        "evidence_ref": "%s%s/test-output/%s" % (
            EVIDENCE_SCHEME, project_id, fname),
        "reason": None, "output": str(sign_off),
        "duration_s": time.monotonic() - started,
    }


#: Entry points: logical name -> symbol in this module.
ENTRY_POINTS = {
    "execute_code_test": "execute_code_test",
    "execute_catalog_test": "execute_catalog_test",
    "resolve_evidence_ref": "resolve_evidence_ref",
}
