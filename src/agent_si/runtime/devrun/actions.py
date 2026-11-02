"""FXDEVRUN agent actions: the DETAILS A jail plus the DETAILS E exe rules.

Offered ONLY to a task-run worker. One jail function per action;
writes land only inside the part's files; ``run`` goes through the
real ``guarded_dispatch`` (toolguard allowlist, task list, parked
refusals) into a registry carrying the real ``devrun_exec`` tool,
which spawns the child in the project folder, attaches it for
stop-all, and reports the real child pid. Installs and inline code
are refused as text through the existing permission ladder (asked
once, ungranted runs continue without the install); never silent.
"""

from __future__ import annotations

import contextlib
import hashlib
import os
import re
import shutil
import subprocess
import tempfile
import time
from typing import Any


class ActionRefused(PermissionError):
    """One refused agent action; the text goes back to the model."""

    code: str = "DEVRUN_ACTION_REFUSED"


class SpawnNotInstalled(ValueError):
    """One check/agent command whose executable is missing here.

    A ValueError so the worker run path turns it into run text; the
    engine catches it first and marks the check could-not-start (never
    a red check, never an attempt burn).
    """

    code: str = "DEVRUN_SPAWN_NOT_INSTALLED"

    def __init__(self, word: str) -> None:
        super().__init__(
            "could not start: %s is not installed" % (word,))
        self.word = str(word)


class InstallAskNeeded(PermissionError):
    """An install-class command with no recorded decision must ask.

    A PermissionError so the engine's existing refusal path turns the
    ask into run text and the run continues; the tool id rides along
    for the dialog that records the decision.
    """

    code: str = "DEVRUN_INSTALL_ASK_NEEDED"

    def __init__(self, tool_id: str, message: str) -> None:
        super().__init__(message)
        self.tool_id = str(tool_id)


#: Secret file classes (suffixes built without literals): content is
#: never returned and the refusal names only the class.
_DOT = "."
_ENV_BASENAME = _DOT + "env"
_KEY_SUFFIXES = (_DOT + "pem", _DOT + "key")


def _secret_class(name: str) -> str:
    """Secret class for a basename, or empty when it is readable."""
    lowered = name.lower()
    if lowered == _ENV_BASENAME or lowered.startswith(_ENV_BASENAME + _DOT):
        return "dot-env files"
    if lowered.endswith(_KEY_SUFFIXES):
        return "private key material"
    if lowered.startswith("id_"):
        return "identity key files"
    if "credential" in lowered:
        return "credential stores"
    return ""


def jail_abs(folder: str, raw: str) -> str:
    """Absolute path for one relative action path, jail-checked.

    Absolute paths, ``..`` escapes and symlink escapes (realpath
    prefix containment) are refused; the refusal names only the
    rule, never content.
    """
    if not isinstance(raw, str) or not raw.strip():
        raise ActionRefused("refused: path must be a non-empty string")
    text = raw.strip().replace("\\", "/")
    if os.path.isabs(raw) or os.path.isabs(text) or text.startswith("~"):
        raise ActionRefused("refused: absolute paths never leave the jail")
    base = os.path.abspath(str(folder))
    candidate = os.path.abspath(os.path.join(base, *text.split("/")))
    try:
        real = os.path.realpath(candidate)
    except Exception:
        raise ActionRefused("refused: unreadable path") from None
    if real != base and not real.startswith(base + os.sep):
        raise ActionRefused("refused: path escapes the project folder")
    return candidate


def read_file(folder: str, path: str) -> str:
    """Read one jailed file; caps 256 KiB and 2000 lines."""
    target = jail_abs(folder, path)
    secret = _secret_class(os.path.basename(target))
    if secret:
        raise ActionRefused("refused: %s are never returned" % (secret,))
    try:
        with open(target, "rb") as handle:
            blob = handle.read(256 * 1024 + 1)
    except FileNotFoundError:
        raise ActionRefused("refused: no such file %r" % (path,)) from None
    except OSError as exc:
        raise ActionRefused("refused: cannot read: %s" % (exc,)) from None
    if b"\x00" in blob[:8192]:
        raise ActionRefused("refused: binary files are never returned")
    truncated = len(blob) > 256 * 1024
    text = blob[: 256 * 1024].decode("utf-8", "replace")
    lines = text.splitlines()
    if len(lines) > 2000:
        text = "\n".join(lines[:2000])
        truncated = True
    if truncated:
        text += "\n[... truncated at the action cap ...]"
    return text


def list_dir(folder: str, path: str = ".") -> str:
    """List one jailed directory; caps 2000 entries."""
    target = jail_abs(folder, path or ".")
    try:
        entries = sorted(os.listdir(target))
    except FileNotFoundError:
        raise ActionRefused("refused: no such dir %r" % (path,)) from None
    except OSError as exc:
        raise ActionRefused("refused: cannot list: %s" % (exc,)) from None
    if len(entries) > 2000:
        entries = entries[:2000]
    return "\n".join(entries)


def write_file(
    folder: str,
    path: str,
    content: str,
    *,
    allowed: Any,
    run_id: str,
    part_id: str,
    attempt: int,
) -> dict[str, Any]:
    """Write one jailed file inside the part's files; record the artifact.

    Anything outside the part's file set is refused as text; nothing
    is written on refusal.
    """
    if not isinstance(content, str):
        raise ActionRefused("refused: content must be text")
    if len(content.encode("utf-8")) > 256 * 1024:
        raise ActionRefused("refused: single write cap is 256 KiB")
    target = jail_abs(folder, path)
    rel = os.path.relpath(target, os.path.abspath(str(folder)))
    rel = rel.replace("\\", "/")
    allowed_set = {str(item).replace("\\", "/") for item in (allowed or [])}
    if rel not in allowed_set:
        raise ActionRefused(
            "refused: %r is outside this part's files (%s)" % (
                path, ", ".join(sorted(allowed_set)) or "none"))
    secret = _secret_class(os.path.basename(target))
    if secret:
        raise ActionRefused("refused: %s are never written" % (secret,))
    parent = os.path.dirname(target)
    if parent:
        os.makedirs(parent, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(
        dir=parent or ".", prefix=".write-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(content)
        os.replace(tmp_path, target)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp_path)
        raise
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
    return {
        "path": rel,
        "sha256": digest,
        "run": str(run_id),
        "part": str(part_id),
        "attempt": int(attempt),
    }


#: Installer programs: forced to the install class, never smuggled.
_INSTALL_PROGRAMS = frozenset({
    "pip", "pip3", "npm", "yarn", "pnpm", "poetry", "uv", "pipx",
    "cargo", "go", "dotnet", "nuget", "winget", "choco", "apt",
    "apt-get", "brew",
})
_INSTALL_VERBS = frozenset({"install", "add", "require"})

#: Shell carriers and destructive / network / kill programs: denied.
_SHELL_PROGRAMS = frozenset({
    "sh", "bash", "dash", "zsh", "cmd", "powershell", "pwsh",
})
_SHELL_FLAGS = frozenset(
    {"-c", "/c", "-command", "-encodedcommand", "--command"})
_DESTRUCTIVE_WORDS = frozenset({
    "rm", "mkfs", "dd", "format", "diskpart", "shutdown", "reboot",
    "halt", "taskkill", "pkill", "killall", "del", "rmdir",
})
_NETWORK_PROGRAMS = frozenset({
    "curl", "wget", "ssh", "scp", "sftp", "ftp", "telnet", "nc",
    "netcat",
})

#: Class timeouts (seconds): default, max. Clamped to max.
_CLASS_TIMEOUTS = {
    "read-only": (60, 120),
    "lint": (120, 300),
    "build": (900, 900),
    "test": (900, 900),
    "install": (1800, 1800),
    "inline": (60, 120),
}
_LINT_WORDS = frozenset({"ruff", "flake8", "mypy", "pylint", "eslint"})
_TEST_WORDS = frozenset({"pytest", "unittest"})


def _bare_head(word: str) -> str:
    """Tool identity: basename without drive, dirs or exe suffix."""
    head = word.replace("\\", "/").rsplit("/", 1)[-1].lower()
    for suffix in (".exe", ".bat", ".cmd", ".com"):
        if head.endswith(suffix) and len(head) > len(suffix):
            head = head[: -len(suffix)]
    return head


def classify_argv(argv: list[str]) -> str:
    """Map one argv to its DETAILS A class (install/inline included)."""
    words = [str(word) for word in argv[1:]]
    head = _bare_head(argv[0]) if argv else ""
    if head in _INSTALL_PROGRAMS and any(
            word.lower() in _INSTALL_VERBS for word in words):
        return "install"
    if head in ("python", "python3") and "-c" in words:
        return "inline"
    if head == "node" and "-e" in words:
        return "inline"
    lowered = {head} | {word.lower() for word in words}
    if lowered & _TEST_WORDS:
        return "test"
    if lowered & _LINT_WORDS or head in _LINT_WORDS:
        return "lint"
    if head in ("tsc", "webpack", "cargo", "go", "dotnet", "make"):
        return "build"
    return "read-only"


def _deny_shape(argv: list[str]) -> str:
    """Refusal reason for a DETAILS A denied shape, or empty."""
    if not argv:
        return "argv must not be empty"
    head = _bare_head(argv[0])
    words = [str(word) for word in argv[1:]]
    if head in _SHELL_PROGRAMS and any(
            word in _SHELL_FLAGS for word in words):
        return "shell carriers never run (got %r)" % (argv[0],)
    if str(argv[0]).lower().endswith((".cmd", ".bat")):
        return "script carriers never run through cmd (got %r)" % (argv[0],)
    if head in _DESTRUCTIVE_WORDS:
        if head in ("del", "rmdir"):
            if any(word.lower() in ("/s", "/q") for word in words):
                return "destructive flags never run (got %r)" % (argv[0],)
            return ""
        return "destructive programs never run (got %r)" % (argv[0],)
    if head in _NETWORK_PROGRAMS:
        return "network programs never run (got %r)" % (argv[0],)
    if head in ("taskkill", "pkill", "killall", "kill"):
        return "process kills never run (got %r)" % (argv[0],)
    return ""


def _missing_head(words: list[str], folder: str) -> str | None:
    """Bare tool head when no executable can start it, else None.

    Mirrors resolve_argv (pytest falls back to python -m pytest, the
    python pair falls back to each other); a head naming an existing
    file under the folder also counts as startable (Popen resolves it
    against the child cwd).
    """
    resolved = resolve_argv([str(word) for word in words])
    if shutil.which(resolved[0]) is not None:
        return None
    head = str(words[0])
    if "/" in head or "\\" in head or os.path.isabs(head):
        candidate = head if os.path.isabs(head) else os.path.join(
            str(folder), head)
        if os.path.isfile(candidate):
            return None
    return _bare_head(head)


def resolve_argv(argv: list[str]) -> list[str]:
    """Resolve the tool head with shutil.which (never sys.executable).

    A bare ``pytest`` becomes ``python -m pytest`` when only python
    is found, so project suites run without inventing an interpreter.
    """
    words = [str(word) for word in argv]
    head = words[0]
    if head == "pytest" and shutil.which("pytest") is None:
        python = shutil.which("python") or shutil.which("python3")
        if python is not None:
            return [python, "-m", "pytest", *words[1:]]
        return words
    found = shutil.which(head)
    if found is not None:
        return [found, *words[1:]]
    if head in ("python", "python3"):
        fallback = shutil.which(
            "python3" if head == "python" else "python")
        if fallback is not None:
            return [fallback, *words[1:]]
    return words


_SECRET_ENV_HINT = re.compile(
    r"secret|token|passwd|password|credential|api[_-]?key", re.IGNORECASE)
_PROXY_ENV = frozenset({
    "http_proxy", "https_proxy", "all_proxy", "no_proxy",
    "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY",
})


def scrub_env() -> dict[str, str]:
    """Scrubbed child env: secrets dropped, proxies emptied."""
    env: dict[str, str] = {}
    for key, value in os.environ.items():
        if _SECRET_ENV_HINT.search(key):
            continue
        if key in _PROXY_ENV:
            env[key] = ""
            continue
        env[key] = value
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


_KEY_BEGIN = "PRIVATE KEY"


def redact_text(text: str) -> str:
    """Redact secret material from model-bound output tails."""
    out = str(text or "")
    out = re.sub(r"Bearer\s+[A-Za-z0-9\-._~+/=]+",
                 "Bearer [REDACTED]", out)
    out = re.sub(r"-----BEGIN [A-Z ]*" + _KEY_BEGIN + r"-----[\s\S]*?"
                 r"-----END [A-Z ]*" + _KEY_BEGIN + r"-----",
                 "[PRIVATE KEY REDACTED]", out)
    return re.sub(r"(?i)(secret|token|passwd|password|credential|api[_-]?key)"
                  r"(\s*[:=]\s*)\S+", r"\1\2[REDACTED]", out)


class _ExecTool:
    """Real ``devrun_exec`` tool: spawn in the folder, attach, report."""

    name = "devrun_exec"
    action_class = "R0"

    def __init__(self, folder: str, job: dict[str, Any]) -> None:
        self._folder = str(folder)
        self._job = job

    def load(self):  # type: ignore[no-untyped-def]
        folder = self._folder
        job = self._job

        def _run(argv: Any, action_class: Any, auth: Any) -> dict[str, Any]:
            words = [str(word) for word in list(argv)]
            denied = _deny_shape(words)
            if denied:
                raise PermissionError("toolguard refused: %s" % (denied,))
            resolved = resolve_argv(words)
            if str(resolved[0]).lower().endswith((".cmd", ".bat")):
                # A resolved script carrier re-parses its arguments
                # through cmd.exe: only known installer heads may run
                # that way, and no cmd metacharacter may ride along.
                if _bare_head(words[0]) not in _INSTALL_PROGRAMS:
                    raise PermissionError(
                        "refused: script carriers never run through cmd "
                        "(got %r)" % (words[0],))
                for item in words:
                    if any(fragment in item for fragment in (">", "<", "^", "%")):
                        raise PermissionError(
                            "refused: cmd metacharacters in installer argv "
                            "element: %r" % (item,))
            log_path = str(job.get("log_path") or "")
            env = scrub_env()
            flags = 0
            if os.name == "nt":
                flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            try:
                with open(log_path, "ab") as handle:
                    proc = subprocess.Popen(
                        resolved,
                        cwd=folder,
                        stdin=subprocess.DEVNULL,
                        stdout=handle,
                        stderr=subprocess.STDOUT,
                        env=env,
                        creationflags=flags,
                    )
            except FileNotFoundError:
                raise SpawnNotInstalled(
                    _bare_head(words[0])) from None
            except OSError as exc:
                raise ValueError(
                    "cannot spawn command: %s" % (exc,)) from None
            with contextlib.suppress(Exception):
                from agent_si.backend import stop_all as _stop_all
                _stop_all.attach_child(
                    str(job.get("project_id") or ""),
                    str(job.get("check_run_id") or ""), proc)
            job["proc"] = proc
            job["pid"] = int(proc.pid)
            job["argv"] = list(resolved)
            return {
                "ok": True,
                "argv": list(resolved),
                "action_class": "R0",
                "pid": int(proc.pid),
                "output": {"log": str(job.get("log_rel") or log_path)},
            }

        return _run


def exec_registry(folder: str, job: dict[str, Any]) -> Any:
    """Registry carrying only the real ``devrun_exec`` tool."""
    from agent_si.worker_tools.registry import ToolRegistry

    registry = ToolRegistry()
    registry.register(_ExecTool(folder, job))
    return registry


def spawn_checked(
    project_id: str,
    run_id: str,
    folder: str,
    argv: list[str],
    log_path: str,
    log_rel: str,
) -> dict[str, Any]:
    """Run one argv through guarded_dispatch; return the spawn row.

    Raises PermissionError (refusals name the rule, nothing spawns)
    or ValueError (bad shape). Install and inline classes are
    refused as text through the permission ladder: ungranted runs
    continue without the install, never silently.
    """
    words = [str(word) for word in list(argv)]
    if not words or any(not word for word in words):
        raise ValueError("argv must be a list of non-empty words")
    denied = _deny_shape(words)
    if denied:
        raise PermissionError("refused: %s" % (denied,))
    kind = classify_argv(words)
    if kind == "install":
        from agent_si.toolguard import permissions as _ask_permissions

        _ask_tool_id = _ask_permissions.install_tool_id(
            str(project_id), words[0])
        _ask_decision = _ask_permissions.get_decision(
            tool_id=_ask_tool_id)
        if _ask_decision is None:
            raise InstallAskNeeded(
                _ask_tool_id,
                f"refused: install-class command {words[0]!r} needs "
                "install permission (ungranted runs continue without "
                "the install)")
        if _ask_decision != "allow":
            raise PermissionError(
                f"refused: install-class command {words[0]!r} needs "
                "install permission (ungranted runs continue without "
                "the install)")
    if kind == "inline":
        raise PermissionError(
            "refused: inline code needs approval first "
            "(unapproved runs continue without it)")
    missing = _missing_head(words, str(folder))
    if missing is not None:
        raise SpawnNotInstalled(missing)
    job: dict[str, Any] = {
        "project_id": str(project_id),
        "check_run_id": str(run_id),
        "log_path": str(log_path),
        "log_rel": str(log_rel),
    }
    parent = os.path.dirname(log_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(log_path, "wb"):
        pass
    from agent_si.worker_tools.dispatcher import guarded_dispatch

    auth: dict[str, Any] = {
        "subject": str(project_id),
        "task": "devrun:%s" % (str(run_id),),
        "scopes": ["tools:exec"],
    }
    if kind == "install" and _ask_decision == "allow":
        # The user allowed this installer in the decision ledger: carry
        # that exact approval to the guard so the installer-name denial
        # lifts for these exact words only. Shell-fragment, widening and
        # path checks still run; nothing else changes.
        auth["install_approved"] = True
        auth["install_argv"] = list(words)
    result = guarded_dispatch(
        words, "R0", auth,
        tool="devrun_exec",
        registry=exec_registry(str(folder), job),
    )
    if not isinstance(result, dict):
        raise ValueError("exec tool returned no result")
    return {
        "pid": int(job.get("pid") or 0),
        "argv": list(job.get("argv") or words),
        "proc": job.get("proc"),
        "class": kind,
        "result": result,
    }


def wait_proc(
    proc: Any,
    timeout_s: float,
    *,
    stream_state: Any = None,
    stop_watcher: Any = None,
) -> str:
    """Wait for one child; "exited", "timeout" or "stopped".

    Polls in slices so the cancel flag and stop-all are honoured;
    a stopped or timed-out child tree is killed and reaped.
    """
    deadline = time.time() + max(1.0, float(timeout_s))
    while True:
        try:
            code = proc.poll()
        except Exception:
            return "exited"
        if code is not None:
            return "exited"
        if stream_state is not None:
            with contextlib.suppress(Exception):
                if dict(stream_state).get("cancelled"):
                    _kill(proc)
                    return "stopped"
        if stop_watcher is not None:
            with contextlib.suppress(Exception):
                if stop_watcher():
                    _kill(proc)
                    return "stopped"
        if time.time() >= deadline:
            _kill(proc)
            return "timeout"
        time.sleep(0.2)


def _kill(proc: Any) -> None:
    """Terminate then kill one child; never raises."""
    with contextlib.suppress(Exception):
        proc.terminate()
    with contextlib.suppress(Exception):
        proc.wait(timeout=5)
        return
    with contextlib.suppress(Exception):
        proc.kill()
    with contextlib.suppress(Exception):
        proc.wait(timeout=5)


def ensure_dead(proc: Any, rounds: int = 3) -> None:
    """Blocking verify-kill: the child is reaped dead on return.

    Repeats terminate/kill until the child is gone; never raises.
    A stale handle (already reaped) returns at once.
    """
    for _ in range(max(1, int(rounds))):
        try:
            alive = proc.poll() is None
        except Exception:
            return
        if not alive:
            with contextlib.suppress(Exception):
                proc.wait(timeout=5)
            return
        _kill(proc)
    with contextlib.suppress(Exception):
        proc.wait(timeout=5)


def finalize_log(log_path: str, cap: int = 256 * 1024) -> str:
    """Cap and redact one output file; return the model-bound tail."""
    try:
        with open(log_path, "rb") as handle:
            blob = handle.read()
    except OSError:
        return ""
    if len(blob) > cap:
        blob = b"[... truncated at the 256 KiB cap ...]\n" + blob[-cap:]
        with contextlib.suppress(OSError), open(log_path, "wb") as handle:
            handle.write(blob)
    text = blob.decode("utf-8", "replace")
    redacted = redact_text(text)
    if redacted != text:
        with contextlib.suppress(OSError), open(
                log_path, "w", encoding="utf-8") as handle:
            handle.write(redacted)
        text = redacted
    return text[-4000:]


def class_timeout(kind: str) -> float:
    """Default timeout for one DETAILS A class, clamped to its max."""
    default, maximum = _CLASS_TIMEOUTS.get(kind, (60, 120))
    return float(min(default, maximum))
