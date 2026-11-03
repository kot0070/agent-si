"""K03 FXCATALOG lane: QA runner host (subprocess jail + result envelope).

Frozen contract F3/F3b/F3c/F3d (and the packaged-exe delta):

* The app runs ``python <abs host.py> <runner>`` where ``<runner>`` is a
  RUNNER_ID living in ``runners/`` or an absolute ``.py`` path.
* Input JSON arrives on stdin: ``project_root``, ``test_id``, ``params``,
  ``budgets`` (``timeout_s``, ``evidence_dir``).
* Exactly one result JSON goes to stdout; exit 0 means transport ok and
  the verdict lives in the payload. Unparseable or empty child JSON is
  BLOCKED. Statuses: PASS FAIL BLOCKED UNSUPPORTED. UNSUPPORTED means
  the project gave the runner no input, never PASS.
* Result keys: test_id, runner_id, status, reason, assertions, evidence,
  child_pid, child_env_keys, proxies_emptied. PASS with assertions < 1
  is rewritten to BLOCKED (zero_assertions).
* Each runner file declares RUNNER_ID (== filename stem), RUNNER_VERSION,
  RUNNER_TIMEOUT_S, RUNNER_NEEDS and RUNNER_DESCRIPTION; the host
  validates the header before running and rejects mismatches (BLOCKED).
* Jail: child cwd is project_root; the child may write only under
  project_root + evidence_dir; the child env is an allowlist
  (SystemRoot, PATH, TEMP, TMP, LANG, PYTHONIOENCODING, PYTHONUTF8)
  plus runner-declared extra names, minus any key matching
  ``secret|token|passwd|password|credential|api[_-]?key``
  (case-insensitive); proxy variables are emptied. Timeout defaults to
  60 s and caps at 300 s; stdout caps at 256 KiB; the child is polled
  every 0.2 s, granted 5 s to die, and the whole child tree is killed.
  The real child pid is recorded. Network checks are loopback-only
  (enforced inside the runners); a tool that is not installed is
  BLOCKED naming the tool. Never real services, payments, credentials.
* Packaged-exe delta: when ``sys.frozen`` is set the runner is launched
  as ``[sys.executable, --qa-runner, <runner id>]`` with the same
  stdin/stdout contract; otherwise it is ``[sys.executable, runner.py]``.
  ``AGENT_SI_QA_FROZEN_SIM`` (JSON list prefix, QA probes only) routes
  through the same frozen dispatch path without a frozen exe.

Stdlib only. No DATA reads at runtime. No hardcoded PASS.
"""

from __future__ import annotations

import ast
import contextlib
import json
import os
import re
import subprocess
import sys
import time

try:
    from agent_si.backend.proc_tree import quiet_flags
except ImportError:  # bare-script run without src on sys.path
    def quiet_flags() -> int:
        """CREATE_NO_WINDOW on Windows, else 0 (script-mode fallback)."""
        return int(getattr(subprocess, "CREATE_NO_WINDOW", 0))

RUNNER_ID = "host"
RUNNER_VERSION = "1.0.0"
RUNNER_TIMEOUT_S = 60
RUNNER_NEEDS = {
    "tools": [],
    "network": False,
    "project_tooling": False,
    "local_subprocess": True,
    "env": [],
}
RUNNER_DESCRIPTION = (
    "QA runner host: launches one set-A runner as a jailed real "
    "subprocess and emits exactly one F3b result JSON."
)

HOST_VERSION = "1.0.0"

#: Allowed result statuses (F3).
STATUSES = ("PASS", "FAIL", "BLOCKED", "UNSUPPORTED")

#: Base child environment allowlist (F3d).
_BASE_ENV_ALLOW = (
    "SystemRoot",
    "PATH",
    "TEMP",
    "TMP",
    "LANG",
    "PYTHONIOENCODING",
    "PYTHONUTF8",
)

#: Proxy variables: emptied in the child, never inherited (F3d).
_PROXY_VARS = (
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
)

#: Secret-like keys are dropped from the child env (F3d).
_SECRET_RE = re.compile(
    r"secret|token|passwd|password|credential|api[_-]?key", re.IGNORECASE
)

#: Stdout capture cap, bytes (F3d: 256 KiB).
_STDOUT_CAP = 262144

_DEFAULT_TIMEOUT_S = 60.0
_MAX_TIMEOUT_S = 300.0
_POLL_S = 0.2
_KILL_GRACE_S = 5.0


def _runners_dir() -> str:
    """Return the directory holding the runner files."""
    return os.path.dirname(os.path.abspath(__file__))


def _resolve_runner(ref: str):
    """Map a host argv ref to (runner_path, runner_id).

    ``ref`` is a RUNNER_ID under runners/ or an absolute ``.py`` path.
    Returns (None, ref) when the file cannot be located.
    """
    name = (ref or "").strip()
    if not name:
        return None, ""
    if name.endswith(".py") and os.path.isfile(name):
        path = os.path.abspath(name)
        return path, os.path.splitext(os.path.basename(path))[0]
    candidate = os.path.join(_runners_dir(), name + ".py")
    if os.path.isfile(candidate):
        return candidate, name
    return None, name


def _read_header(path: str):
    """Parse RUNNER_* header constants without executing the file.

    Returns (header_dict, None) or (None, reason) for a bad header.
    """
    try:
        with open(path, "r", encoding="utf-8") as handle:
            text = handle.read()
    except OSError as exc:
        return None, "bad_header unreadable: %s" % exc
    try:
        tree = ast.parse(text, filename=path)
    except SyntaxError as exc:
        return None, "bad_header syntax error: %s" % exc
    found = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name):
            continue
        if target.id not in (
            "RUNNER_ID",
            "RUNNER_VERSION",
            "RUNNER_TIMEOUT_S",
            "RUNNER_NEEDS",
            "RUNNER_DESCRIPTION",
        ):
            continue
        try:
            found[target.id] = ast.literal_eval(node.value)
        except (ValueError, SyntaxError):
            return None, "bad_header %s not a literal" % target.id
    for key in (
        "RUNNER_ID",
        "RUNNER_VERSION",
        "RUNNER_TIMEOUT_S",
        "RUNNER_NEEDS",
        "RUNNER_DESCRIPTION",
    ):
        if key not in found:
            return None, "bad_header missing %s" % key
    stem = os.path.splitext(os.path.basename(path))[0]
    if found["RUNNER_ID"] != stem:
        return None, "bad_header RUNNER_ID != filename stem"
    if not isinstance(found["RUNNER_VERSION"], str) or not found["RUNNER_VERSION"]:
        return None, "bad_header RUNNER_VERSION must be a non-empty string"
    timeout = found["RUNNER_TIMEOUT_S"]
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)):
        return None, "bad_header RUNNER_TIMEOUT_S must be a number"
    if not timeout > 0:
        return None, "bad_header RUNNER_TIMEOUT_S must be positive"
    needs = found["RUNNER_NEEDS"]
    if not isinstance(needs, dict):
        return None, "bad_header RUNNER_NEEDS must be a dict"
    for key in ("tools", "network", "project_tooling", "local_subprocess"):
        if key not in needs:
            return None, "bad_header RUNNER_NEEDS missing %s" % key
    if not isinstance(needs["tools"], list) or not all(
        isinstance(item, str) for item in needs["tools"]
    ):
        return None, "bad_header RUNNER_NEEDS tools must be a string list"
    for key in ("network", "project_tooling", "local_subprocess"):
        if not isinstance(needs[key], bool):
            return None, "bad_header RUNNER_NEEDS %s must be bool" % key
    extra = needs.get("env", [])
    if not isinstance(extra, list) or not all(
        isinstance(item, str) for item in extra
    ):
        return None, "bad_header RUNNER_NEEDS env must be a string list"
    if not isinstance(found["RUNNER_DESCRIPTION"], str) or not found[
        "RUNNER_DESCRIPTION"
    ].strip():
        return None, "bad_header RUNNER_DESCRIPTION must be non-empty"
    return found, None


def _build_env(extra_names) -> tuple:
    """Build the jailed child env; return (env, keys, proxies_emptied)."""
    env: dict = {}
    for key in list(_BASE_ENV_ALLOW) + [str(item) for item in (extra_names or [])]:
        if _SECRET_RE.search(key):
            continue
        value = os.environ.get(key)
        if value is None:
            continue
        if not isinstance(value, str):
            continue
        env[key] = value
    emptied = False
    for key in _PROXY_VARS:
        if key in env:
            del env[key]
        parent = os.environ.get(key)
        if parent:
            emptied = True
        env[key] = ""
    return env, sorted(env.keys()), emptied


def _kill_tree(proc: "subprocess.Popen") -> None:
    """Kill the whole child tree, then the child itself."""
    with contextlib.suppress(Exception):
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                capture_output=True,
                timeout=10,
                creationflags=quiet_flags(),
            )
        else:
            import signal

            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    with contextlib.suppress(Exception):
        proc.kill()


def _run_child(argv, stdin_bytes, cwd, env, timeout_s):
    """Run the child; return (returncode, stdout, timed_out, pid)."""
    if os.name == "nt":
        proc = subprocess.Popen(
            argv,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=cwd,
            env=env,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
            | quiet_flags(),
        )
    else:
        proc = subprocess.Popen(
            argv,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=cwd,
            env=env,
            start_new_session=True,
        )
    pid = proc.pid
    try:
        proc.stdin.write(stdin_bytes)
    except (BrokenPipeError, OSError):
        pass
    try:
        with contextlib.suppress(Exception):
            proc.stdin.close()
    except Exception:
        pass
    deadline = time.monotonic() + timeout_s
    timed_out = False
    while True:
        if proc.poll() is not None:
            break
        if time.monotonic() >= deadline:
            timed_out = True
            break
        time.sleep(_POLL_S)
    if timed_out:
        _kill_tree(proc)
        end = time.monotonic() + _KILL_GRACE_S
        while proc.poll() is None and time.monotonic() < end:
            time.sleep(_POLL_S)
        if proc.poll() is None:
            _kill_tree(proc)
    try:
        out, _ = proc.communicate(timeout=_KILL_GRACE_S)
    except Exception:
        out = b""
    return proc.returncode, out or b"", timed_out, pid


def _blocked(test_id, runner_id, reason, pid, keys, emptied):
    """Build a BLOCKED envelope (transport ok, verdict BLOCKED)."""
    return {
        "test_id": test_id or "",
        "runner_id": runner_id or "",
        "status": "BLOCKED",
        "reason": reason,
        "assertions": 0,
        "evidence": [],
        "child_pid": pid or 0,
        "child_env_keys": list(keys or []),
        "proxies_emptied": bool(emptied),
    }


def main(argv=None) -> int:
    """Run one runner as a jailed subprocess; print one result JSON."""
    args = list(sys.argv[1:] if argv is None else argv)
    ref = args[0] if args else ""
    runner_path, runner_id = _resolve_runner(ref) if ref else (None, "")

    def emit(payload) -> int:
        sys.stdout.write(json.dumps(payload) + "\n")
        sys.stdout.flush()
        return 0

    if not ref:
        return emit(_blocked("", "", "missing_runner", 0, [], False))

    try:
        raw = sys.stdin.buffer.read()
    except Exception:
        return emit(_blocked("", runner_id, "host_bad_input", 0, [], False))
    try:
        request = json.loads(raw.decode("utf-8"))
    except Exception:
        return emit(_blocked("", runner_id, "host_bad_input", 0, [], False))
    if not isinstance(request, dict):
        return emit(_blocked("", runner_id, "host_bad_input", 0, [], False))

    test_id = request.get("test_id", "")
    if not isinstance(test_id, str):
        test_id = ""
    params = request.get("params", {})
    if not isinstance(params, dict):
        params = {}
    budgets = request.get("budgets", {})
    if not isinstance(budgets, dict):
        budgets = {}
    project_root = request.get("project_root", "")
    if not isinstance(project_root, str) or not project_root:
        return emit(
            _blocked(test_id, runner_id, "bad_project_root", 0, [], False)
        )
    project_root = os.path.abspath(project_root)
    if not os.path.isdir(project_root):
        return emit(
            _blocked(test_id, runner_id, "bad_project_root", 0, [], False)
        )
    try:
        timeout_s = float(budgets.get("timeout_s", _DEFAULT_TIMEOUT_S))
    except (TypeError, ValueError):
        timeout_s = _DEFAULT_TIMEOUT_S
    if not timeout_s > 0:
        timeout_s = _DEFAULT_TIMEOUT_S
    timeout_s = min(timeout_s, _MAX_TIMEOUT_S)
    evidence_dir = budgets.get("evidence_dir", "")
    if not isinstance(evidence_dir, str) or not evidence_dir:
        evidence_dir = os.path.join(project_root, "qa_evidence")
    evidence_dir = os.path.abspath(evidence_dir)
    try:
        os.makedirs(evidence_dir, exist_ok=True)
    except OSError:
        return emit(
            _blocked(test_id, runner_id, "bad_evidence_dir", 0, [], False)
        )

    frozen = bool(getattr(sys, "frozen", False))
    sim_prefix = None
    sim_raw = os.environ.get("AGENT_SI_QA_FROZEN_SIM")
    if sim_raw:
        try:
            sim_prefix = json.loads(sim_raw)
        except Exception:
            sim_prefix = None
        if (
            not isinstance(sim_prefix, list)
            or not sim_prefix
            or not all(isinstance(item, str) and item for item in sim_prefix)
        ):
            return emit(
                _blocked(test_id, runner_id, "host_bad_sim", 0, [], False)
            )

    if runner_path is None or not os.path.isfile(runner_path):
        if (frozen or sim_prefix) and runner_id:
            header = None
        else:
            return emit(
                _blocked(test_id, runner_id, "unknown_runner", 0, [], False)
            )
    else:
        header, header_reason = _read_header(runner_path)
        if header is None:
            return emit(
                _blocked(
                    test_id, runner_id, header_reason or "bad_header", 0, [], False
                )
            )

    if header is not None:
        env, env_keys, emptied = _build_env(header["RUNNER_NEEDS"].get("env", []))
    else:
        env, env_keys, emptied = _build_env([])

    child_input = {
        "project_root": project_root,
        "test_id": test_id,
        "params": params,
        "budgets": {"timeout_s": timeout_s, "evidence_dir": evidence_dir},
    }
    stdin_bytes = json.dumps(child_input).encode("utf-8")

    if frozen:
        child_argv = [sys.executable, "--qa-runner", runner_id]
    elif sim_prefix:
        child_argv = list(sim_prefix) + ["--qa-runner", runner_id]
    else:
        child_argv = [sys.executable, runner_path]

    try:
        returncode, out, timed_out, pid = _run_child(
            child_argv, stdin_bytes, project_root, env, timeout_s
        )
    except Exception as exc:
        return emit(
            _blocked(
                test_id, runner_id, "host_spawn_failed: %s" % exc, 0, env_keys,
                emptied,
            )
        )

    if timed_out:
        return emit(
            _blocked(
                test_id, runner_id, "child_timeout", pid, env_keys, emptied
            )
        )
    if returncode != 0:
        return emit(
            _blocked(
                test_id, runner_id, "child_exit_%s" % returncode, pid, env_keys,
                emptied,
            )
        )
    if not out.strip():
        return emit(
            _blocked(
                test_id, runner_id, "child_empty", pid, env_keys, emptied
            )
        )
    if len(out) > _STDOUT_CAP:
        return emit(
            _blocked(
                test_id, runner_id, "child_stdout_cap", pid, env_keys, emptied
            )
        )
    try:
        payload = json.loads(out.decode("utf-8"))
    except Exception:
        return emit(
            _blocked(
                test_id, runner_id, "child_bad_json", pid, env_keys, emptied
            )
        )
    if not isinstance(payload, dict):
        return emit(
            _blocked(
                test_id, runner_id, "child_bad_json", pid, env_keys, emptied
            )
        )

    status = payload.get("status")
    if status not in STATUSES:
        return emit(
            _blocked(
                test_id, runner_id, "child_bad_status", pid, env_keys, emptied
            )
        )
    if payload.get("runner_id") != runner_id:
        return emit(
            _blocked(
                test_id, runner_id, "child_id_mismatch", pid, env_keys, emptied
            )
        )
    child_test = payload.get("test_id", "")
    if not isinstance(child_test, str) or (test_id and child_test != test_id):
        return emit(
            _blocked(
                test_id, runner_id, "child_id_mismatch", pid, env_keys, emptied
            )
        )
    assertions = payload.get("assertions", 0)
    if isinstance(assertions, bool) or not isinstance(assertions, int):
        return emit(
            _blocked(
                test_id, runner_id, "child_bad_assertions", pid, env_keys,
                emptied,
            )
        )
    if assertions < 0:
        return emit(
            _blocked(
                test_id, runner_id, "child_bad_assertions", pid, env_keys,
                emptied,
            )
        )
    evidence = payload.get("evidence", [])
    if not isinstance(evidence, list) or not all(
        isinstance(item, str) for item in evidence
    ):
        return emit(
            _blocked(
                test_id, runner_id, "child_bad_evidence", pid, env_keys,
                emptied,
            )
        )
    for item in evidence:
        base = os.path.basename(item)
        if not base or base != item or item in (".", ".."):
            return emit(
                _blocked(
                    test_id, runner_id, "child_bad_evidence", pid, env_keys,
                    emptied,
                )
            )
    reason = payload.get("reason", "")
    if not isinstance(reason, str) or not reason:
        reason = "child gave no reason"
    if status == "PASS" and assertions < 1:
        return emit(
            _blocked(
                test_id, runner_id, "zero_assertions", pid, env_keys, emptied
            )
        )
    return emit(
        {
            "test_id": test_id,
            "runner_id": runner_id,
            "status": status,
            "reason": reason,
            "assertions": assertions,
            "evidence": evidence,
            "child_pid": pid,
            "child_env_keys": env_keys,
            "proxies_emptied": emptied,
        }
    )


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # last-resort envelope, transport ok
        try:
            sys.stdout.write(
                json.dumps(
                    {
                        "test_id": "",
                        "runner_id": "",
                        "status": "BLOCKED",
                        "reason": "host_crash: %s" % exc,
                        "assertions": 0,
                        "evidence": [],
                        "child_pid": 0,
                        "child_env_keys": [],
                        "proxies_emptied": False,
                    }
                )
                + "\n"
            )
        except Exception:
            pass
        sys.exit(0)
