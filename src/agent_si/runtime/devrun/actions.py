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
import json
import locale
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
        super().__init__(_missing_tool_line(word))
        self.word = str(word)


#: Where to get a missing tool; a bare PC never auto-installs, so the
#: line names the tool plus its source and the plain next step.
_MISSING_TOOL_SOURCES = {
    "node": "nodejs.org",
    "npm": "nodejs.org",
    "npx": "nodejs.org",
    "python": "python.org",
    "python3": "python.org",
    "py": "python.org",
    "pytest": "python.org",
    "pip": "python.org",
    "pip3": "python.org",
    "git": "git-scm.com",
}


def _missing_tool_line(word: Any) -> str:
    """One plain line for a missing executable: name, source, next step.

    Never a stack, never raw exit text as the headline, never an
    auto-install: the user installs it, then sends the task again.
    """
    try:
        name = str(word)
    except Exception:
        name = ""
    head = name.replace("\\", "/").rsplit("/", 1)[-1].lower()
    for suffix in (".exe", ".bat", ".cmd", ".com"):
        if head.endswith(suffix) and len(head) > len(suffix):
            head = head[: -len(suffix)]
    source = _MISSING_TOOL_SOURCES.get(head, "")
    if source:
        return ("could not start: %s is not installed on this machine; "
                "get it at %s, install it, then send the task again"
                % (name, source))
    return ("could not start: %s is not installed on this machine; "
            "install it, then send the task again" % (name,))


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


class InstallDenied(PermissionError):
    """An install-class command the user denied (FXR4A D6).

    Raised (not returned as text) so a denied installer is never
    swallowed by checks-green success: the note still reaches the
    worker's reply, and the engine closes the part FAILED with the
    plain line. The tool id rides along like the ask does.
    """

    code: str = "DEVRUN_INSTALL_DENIED"

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
        real_base = os.path.realpath(base)
    except Exception:
        raise ActionRefused("refused: unreadable path") from None
    # Compare realpath + normcase on both sides: an 8.3 short form
    # (PCIA~1), a junction alias or a case variant of the folder is
    # the same jail once resolved; escapes still refuse below.
    want = os.path.normcase(real_base)
    got = os.path.normcase(real)
    if got != want and not got.startswith(want + os.sep):
        raise ActionRefused("refused: path escapes the project folder")
    return candidate


def describe_binary(folder: str, path: str) -> str:
    """One-line binary marker for one jailed file; contents never returned.

    Reads ``"<folder>/<path>"`` as bytes only to count and hash it, and
    reports ``"binary file, N bytes, sha256 <hex>"``. Missing or
    unreadable files refuse exactly like read_file; secret-class files
    are never described (the kind refusal wins first).
    """
    target = jail_abs(folder, path)
    secret = _secret_class(os.path.basename(target))
    if secret:
        raise ActionRefused("refused: %s are never returned" % (secret,))
    digest = hashlib.sha256()
    size = 0
    try:
        with open(target, "rb") as handle:
            for chunk in iter(lambda: handle.read(65536), b""):
                digest.update(chunk)
                size += len(chunk)
    except FileNotFoundError:
        raise ActionRefused("refused: no such file %r" % (path,)) from None
    except OSError as exc:
        raise ActionRefused("refused: cannot read: %s" % (exc,)) from None
    return "binary file, %d bytes, sha256 %s" % (size, digest.hexdigest())


def _console_code_page() -> str | None:
    """This console's output code page name (Windows) or None."""
    if os.name != "nt":
        return None
    try:
        import ctypes

        code = ctypes.windll.kernel32.GetConsoleOutputCP()  # type: ignore[attr-defined]
        if code:
            return "cp" + str(int(code))
    except Exception:
        return None
    return None


def _decode_console_text(blob: bytes) -> str:
    """Decode child/file bytes without mojibake or a crash.

    Strict in order: utf-8-sig, then the console code page, cp1251,
    cp866; utf-8 with replace is the last resort and never raises.
    """
    candidates = ["utf-8-sig"]
    console = _console_code_page()
    if console is not None:
        candidates.append(console)
    else:
        with contextlib.suppress(Exception):
            preferred = locale.getpreferredencoding(False)
            if preferred:
                candidates.append(preferred)
    candidates.extend(["cp1251", "cp866"])
    seen: set[str] = set()
    for encoding in candidates:
        key = str(encoding).lower().replace("_", "-")
        if key in seen:
            continue
        seen.add(key)
        try:
            return bytes(blob).decode(encoding, "strict")
        except Exception:
            continue
    return bytes(blob).decode("utf-8", "replace")


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
    text = _decode_console_text(blob[: 256 * 1024])
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


#: Antivirus-lock retry: a transient PermissionError around file
#: opens and replaces is retried this many times, this far apart.
_AV_LOCK_ATTEMPTS = 3
_AV_LOCK_PAUSE_S = 0.2


def _retry_av_lock(func: Any) -> Any:
    """Run one file op, retrying AV-lock PermissionError 3x, 0.2 s apart."""
    last: BaseException | None = None
    for attempt in range(_AV_LOCK_ATTEMPTS):
        try:
            return func()
        except PermissionError as exc:
            last = exc
            if attempt + 1 < _AV_LOCK_ATTEMPTS:
                time.sleep(_AV_LOCK_PAUSE_S)
    assert last is not None
    raise last


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
    # FXPARALLEL+int atomic-write: temp file plus replace in the same
    # folder, so a peer part never reads a half-written file. The
    # temp name is dot-prefixed plus .tmp (never a project file,
    # never inside the part's allowed list) and is removed on failure.
    fd, tmp_path = _retry_av_lock(lambda: tempfile.mkstemp(
        dir=parent or ".", prefix=".write-", suffix=".tmp"))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(content)
        _retry_av_lock(lambda: os.replace(tmp_path, target))
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
#: npx rides here verb-gated like the rest: `npx install` asks while
#: `npx tsc` (no install verb) keeps its normal class.
_INSTALL_PROGRAMS = frozenset({
    "pip", "pip3", "npm", "npx", "yarn", "pnpm", "poetry", "uv", "uvx",
    "pipx", "corepack", "cargo", "go", "dotnet", "nuget", "winget",
    "choco", "apt", "apt-get", "brew",
})
_INSTALL_VERBS = frozenset({"install", "add", "require"})

#: Fetch-and-run heads: always the install class (they download before
#: they run, whatever the subcommand). `npx`/`pipx`/`uvx`/`corepack`
#: bare, plus the `dlx`/`exec` fetch verbs of the JS managers.
_ALWAYS_INSTALL_HEADS = frozenset({"npx", "uvx", "pipx", "corepack"})
_FETCH_VERBS = frozenset({"dlx", "exec"})

#: Python launchers whose `-m <module>` form runs the module as the
#: effective tool (workspace `.venv` pythons resolve here by basename,
#: so they stay project tools unless the module installs).
_PYTHON_LAUNCHERS = frozenset({"python", "python3", "py"})

#: Managers whose `run` verb executes project scripts.
_SCRIPT_MANAGERS = frozenset({"npm", "yarn", "pnpm", "bun"})

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


#: Installer invocations inside a package.json script body: any of
#: these turns the manager's run of that script into the install class.
_INSTALL_SCRIPT_TOKENS = re.compile(
    r"(?<![\w-])(npm\s+(i|install|ci|add)|pip\s+install|"
    r"uv\s+pip\s+(install|sync)|npx\b|yarn\s+add|pnpm\s+add|"
    r"bun\s+add|poetry\s+add|pipx\s+install|conda\s+install|"
    r"winget\s+install|choco\s+install|apt(-get)?\s+install)"
    r"(?![\w-])",
    re.IGNORECASE)


def _run_script_name(head: str, words: list[str]) -> str:
    """Project script name for a manager run verb, or empty.

    npm runs scripts via run/run-script plus the test/start shorthands;
    yarn/pnpm/bun run a bare script name (their run verb included).
    Anything else (flags, install verbs, unknown shapes) is empty.
    """
    if not words:
        return ""
    first = str(words[0])
    if first in ("run", "run-script"):
        return str(words[1]) if len(words) > 1 else ""
    if head == "npm" and first in ("test", "start"):
        return first
    if head in ("yarn", "pnpm", "bun"):
        if first.startswith("-") or first.lower() in _INSTALL_VERBS:
            return ""
        return first
    return ""


def _script_runs_install(folder: str, argv: list[str]) -> bool:
    """True when a manager run executes a script that installs.

    Reads only folder/package.json (never executed): the named script
    body is scanned for installer invocations. A missing/unreadable
    package.json, a missing name, or a clean script reads False — the
    manager itself then fails honestly when nothing is there to run, so
    no install can slip through. Never raises.
    """
    try:
        words = [str(word) for word in list(argv)]
        if not words:
            return False
        head = _bare_head(words[0])
        if head not in _SCRIPT_MANAGERS:
            return False
        name = _run_script_name(head, words[1:])
        if not name:
            return False
        path = os.path.join(str(folder), "package.json")
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
        if not isinstance(data, dict):
            return False
        scripts = data.get("scripts")
        if not isinstance(scripts, dict):
            return False
        body = scripts.get(name)
        if not isinstance(body, str):
            return False
        return bool(_INSTALL_SCRIPT_TOKENS.search(body))
    except Exception:
        return False


def _bare_head(word: str) -> str:
    """Tool identity: basename without drive, dirs or exe suffix."""
    head = word.replace("\\", "/").rsplit("/", 1)[-1].lower()
    for suffix in (".exe", ".bat", ".cmd", ".com"):
        if head.endswith(suffix) and len(head) > len(suffix):
            head = head[: -len(suffix)]
    return head


def classify_argv(argv: list[str]) -> str:
    """Map one argv to its DETAILS A class (install/inline included).

    The effective tool head decides: a Python launcher's ``-m <mod>``
    form runs the module (``python -m pip install`` is an install while
    a workspace ``.venv`` python running pytest stays a project tool),
    and a bare installer head with an install verb is an install.
    Project scripts executed through a manager's run verb are NOT
    decided here (no filesystem): spawn_checked upgrades them through
    _script_runs_install when the script text invokes an installer.
    """
    words = [str(word) for word in argv[1:]]
    head = _bare_head(argv[0]) if argv else ""
    effective = head
    if head in _PYTHON_LAUNCHERS and "-m" in words:
        try:
            module = str(words[words.index("-m") + 1])
        except (ValueError, IndexError):
            module = ""
        if module:
            effective = module.strip().lower().rsplit("/", 1)[-1]
    if effective in _ALWAYS_INSTALL_HEADS:
        return "install"
    if effective in ("yarn", "pnpm", "npm") and words[:1] \
            and words[0].lower() in _FETCH_VERBS:
        return "install"
    if effective in _INSTALL_PROGRAMS and any(
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


def _windows_findstr_files(words: list[str]) -> list[str]:
    """Backslash file operands for findstr on Windows (F13).

    Windows findstr cannot open forward-slash paths, so on Windows
    only, for a findstr head, file operands get ``\\`` separators.
    Flags (words starting with ``/`` or ``-``) and the search string
    (the first non-flag word, unless ``/C:`` or ``/G:`` already names
    the pattern or file source) are never touched. Off Windows, or
    for any other head, the words pass through unchanged.
    """
    if os.name != "nt" or not words:
        return words
    if _bare_head(words[0]) != "findstr":
        return words
    lowered = [str(word).lower() for word in words[1:]]
    pattern_sourced = any(
        word == "/c:" or word.startswith("/c:")
        or word == "/g:" or word.startswith("/g:")
        for word in lowered)
    out = [words[0]]
    first_operand = True
    for word in words[1:]:
        text = str(word)
        if text.startswith("/") or text.startswith("-"):
            out.append(text)
            continue
        if first_operand and not pattern_sourced:
            first_operand = False
            out.append(text)
            continue
        out.append(text.replace("/", os.sep))
    return out


def _installer_name(words: list[str]) -> str:
    """Installer name for the ask ledger: the effective installer head.

    A ``-m`` launcher form names its module (``python -m pip install``
    asks as ``pip``, never ``python``); every other installer names
    argv[0]. Only called for the install class, so bare interpreters
    (never install) keep no ask. Matches classify_argv's effective
    head exactly.
    """
    try:
        items = [str(word) for word in list(words or [])]
        if not items:
            return ""
        head = _bare_head(items[0])
        rest = items[1:]
        if head in _PYTHON_LAUNCHERS and "-m" in rest:
            module = str(rest[rest.index("-m") + 1])
            if module and module.strip().lower() in _INSTALL_PROGRAMS:
                return module.strip().lower()
    except Exception:
        pass
    try:
        return str(list(words or [""])[0])
    except Exception:
        return ""


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


#: Bare heads whose Store alias shim never counts as installed.
_ALIAS_SHIM_HEADS = frozenset({"python", "python3", "pytest"})


def _is_windows_store_alias_shim(path: str) -> bool:
    """True when a which() hit is a Windows Store alias shim."""
    try:
        text = str(path or "")
    except Exception:
        return False
    if not text:
        return False
    if "windowsapps" in text.lower():
        return True
    try:
        import os as _os
        if _os.path.isfile(text) and _os.path.getsize(text) == 0:
            return True
    except OSError:
        return False
    return False


def _which_real(name: str):
    """shutil.which filtered for Store alias shims."""
    hit = shutil.which(name)
    if hit is None:
        return None
    if _bare_head(name) in _ALIAS_SHIM_HEADS:
        if _is_windows_store_alias_shim(hit):
            return None
        return hit
    if "windowsapps" in str(hit).lower():
        return None
    return hit


def _missing_head(words: list[str], folder: str) -> str | None:
    """Bare tool head when no executable can start it, else None.

    Mirrors resolve_argv (a project .venv interpreter wins for bare
    python/python3/pytest; pytest falls back to python -m pytest, the
    python pair falls back to each other and then to the py launcher);
    a head naming an existing file under the folder also counts as
    startable (Popen resolves it against the child cwd). A Windows
    Store alias shim (WindowsApps path or zero-byte alias) for
    python/python3/pytest counts as NOT installed and is never
    spawned, not even for --version.
    """
    resolved = resolve_argv([str(word) for word in words], folder)
    prog = str(resolved[0])
    if os.path.isabs(prog):
        if os.path.isfile(prog) and not _is_windows_store_alias_shim(prog):
            if shutil.which(prog) is not None:
                return None
            return None
    else:
        if _which_real(prog) is not None:
            return None
        if shutil.which(prog) is not None and not _is_windows_store_alias_shim(
                str(shutil.which(prog))):
            return None
    head = str(words[0])
    if "/" in head or "\\" in head or os.path.isabs(head):
        candidate = head if os.path.isabs(head) else os.path.join(
            str(folder), head)
        if os.path.isfile(candidate):
            return None
    return _bare_head(head)


#: Bare heads the project .venv interpreter wins for (Windows
#: ``.venv\\Scripts\\python.exe`` first, POSIX ``.venv/bin/python``).
_VENV_HEADS = frozenset({"python", "python3", "pytest"})


def _workspace_python(folder: str, head: str) -> str | None:
    """Project .venv interpreter for a bare head, else None.

    Only exact bare ``python``/``python3``/``pytest`` heads (no dirs,
    no suffixes): the venv python runs them (pytest via ``-m``), so a
    project run never escapes its own environment. The venv lives
    inside the folder, so the jail is unchanged.
    """
    if head not in _VENV_HEADS:
        return None
    for rel in (os.path.join(".venv", "Scripts", "python.exe"),
                os.path.join(".venv", "bin", "python")):
        candidate = os.path.join(str(folder), rel)
        if os.path.isfile(candidate):
            return candidate
    return None


def _workspace_venv_bin(folder: str) -> str | None:
    """Project .venv binary dir for the child PATH, else None."""
    interp = _workspace_python(str(folder), "python")
    if interp is None:
        return None
    return os.path.dirname(interp)


def resolve_argv(argv: list[str], folder: str | None = None) -> list[str]:
    """Resolve the tool head with shutil.which (never sys.executable).

    A project ``.venv`` interpreter wins for bare ``python``,
    ``python3`` and ``pytest`` in that folder (pytest becomes
    ``python -m pytest`` on the venv interpreter). Otherwise a bare
    ``pytest`` becomes ``python -m pytest`` when only python is
    found, the python pair falls back to each other and then to the
    ``py`` launcher, so a PC with only py.exe still starts project
    suites.
    """
    words = [str(word) for word in argv]
    head = words[0]
    if folder is not None and head in _VENV_HEADS:
        venv = _workspace_python(str(folder), head)
        if venv is not None:
            if head == "pytest":
                return [venv, "-m", "pytest", *words[1:]]
            return [venv, *words[1:]]
    if head == "pytest" and _which_real("pytest") is None:
        python = (_which_real("python") or _which_real("python3")
                  or _which_real("py"))
        if python is not None:
            return [python, "-m", "pytest", *words[1:]]
        return words
    found = _which_real(head) if head in ("python", "python3", "pytest", "py") else shutil.which(head)
    if found is not None:
        # Never return a Store alias shim, even when the head itself is absolute.
        if _is_windows_store_alias_shim(found):
            found = None
        else:
            return [found, *words[1:]]
    if found is None and head in ("python", "python3"):
        fallback = _which_real(
            "python3" if head == "python" else "python")
        if fallback is None:
            fallback = _which_real("py")
        if fallback is not None:
            return [fallback, *words[1:]]
    if head in ("python", "python3", "pytest"):
        # Bare head with only an alias shim on PATH: stay bare so _missing_head
        # names the plain missing-tool line (never run the shim).
        return words
    return words


_SECRET_ENV_HINT = re.compile(
    r"secret|token|passwd|password|credential|api[_-]?key", re.IGNORECASE)
_PROXY_ENV = frozenset({
    "http_proxy", "https_proxy", "all_proxy", "no_proxy",
    "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY",
})


def scrub_env() -> dict[str, str]:
    """Scrubbed child env: secrets dropped, proxies emptied.

    The child never inherits host user-site configuration: PYTHONPATH
    and PYTHONHOME are dropped and PYTHONNOUSERSITE=1 is forced, so a
    project run cannot pick up the owner's user site. A project .venv
    keeps working: its own interpreter and paths ride the argv and the
    environment it carries, not these variables.
    """
    env: dict[str, str] = {}
    for key, value in os.environ.items():
        if _SECRET_ENV_HINT.search(key):
            continue
        if key in _PROXY_ENV:
            env[key] = ""
            continue
        env[key] = value
    env.pop("PYTHONPATH", None)
    env.pop("PYTHONHOME", None)
    env["PYTHONNOUSERSITE"] = "1"
    # A7: install managers must never self-fetch. On Windows the
    # Python install-manager alias (and the py launcher) auto-download
    # a full runtime when the child probes `python --version`; pin
    # both switches off. Project-local values (LOCALAPPDATA, APPDATA,
    # HOME, ...) still pass through untouched above.
    env["PYTHON_MANAGER_AUTOMATIC_INSTALL"] = "false"
    env["PYLAUNCHER_ALLOW_INSTALL"] = "0"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    # SG-01: Python children always speak UTF-8, whatever console code
    # page the juror's box uses (cp866/cp1251/cp1252 otherwise mojibake
    # or crash a Ukrainian print). Non-Python tools ignore these.
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
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
            resolved = resolve_argv(words, self._folder)
            if str(resolved[0]).lower().endswith((".cmd", ".bat")):
                # A resolved script carrier re-parses its arguments
                # through cmd.exe: only known installer heads may run
                # that way, and no cmd metacharacter may ride along
                # (& and | would chain a second command through the
                # shim, so they refuse like > < ^ %).
                if _bare_head(words[0]) not in _INSTALL_PROGRAMS:
                    raise PermissionError(
                        "refused: script carriers never run through cmd "
                        "(got %r)" % (words[0],))
                for item in words:
                    if any(fragment in item
                           for fragment in (">", "<", "^", "%", "&", "|")):
                        raise PermissionError(
                            "refused: cmd metacharacters in installer argv "
                            "element: %r" % (item,))
            log_path = str(job.get("log_path") or "")
            env = scrub_env()
            venv_bin = _workspace_venv_bin(self._folder)
            if venv_bin is not None:
                env["PATH"] = (venv_bin + os.pathsep
                               + env.get("PATH", ""))
            flags = _proc_tree.quiet_flags()
            try:
                with _retry_av_lock(
                        lambda: open(log_path, "ab")) as handle:
                    from agent_si.backend import proc_tree as _proc_tree

                    proc = _proc_tree.spawn(
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
    grant_run_id: str = "",
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
    if kind != "install" and _script_runs_install(str(folder), words):
        # An install reached indirectly: the manager runs a project
        # script whose body invokes an installer. Same install class,
        # same permission ask; a workspace program (a .venv python, a
        # node_modules/.bin binary) classifies by its own head above
        # and never lands here.
        kind = "install"
    if kind == "install":
        from agent_si.toolguard import permissions as _ask_permissions

        _ask_name = _installer_name(words)
        _ask_tool_id = _ask_permissions.install_tool_id(
            str(project_id), _ask_name)
        _ask_decision = _ask_permissions.get_decision(
            tool_id=_ask_tool_id)
        # FXR1B project grant: the same installer head and subcommand
        # in this project do not ask again; flags and registries still
        # ask (see install_grant_allows). Read-only here by design.
        _ask_project_grant = (
            _ask_decision is None
            and _ask_permissions.install_grant_allows(
                str(project_id), words))
        # FXR4A D4: an allow covers one run only. Consumed by another
        # run it reads as spent (ask again); consumed by this run it
        # still covers same-run retries. The true run id rides
        # grant_run_id (the positional run id is per-part derived).
        _ask_scope = str(grant_run_id or run_id)
        _ask_run_allow = (
            _ask_project_grant
            or _ask_permissions.decision_allows_run(
                tool_id=_ask_tool_id, run_id=_ask_scope))
        if _ask_decision is None and not _ask_project_grant:
            with contextlib.suppress(Exception):
                _ask_permissions.record_install_request(
                    tool_id=_ask_tool_id,
                    argv=list(words),
                    project_id=str(project_id))
            raise InstallAskNeeded(
                _ask_tool_id,
                f"refused: install-class command {_ask_name!r} needs "
                "install permission (ungranted runs continue without "
                "the install)")
        if not _ask_project_grant and _ask_decision == "deny":
            raise PermissionError(
                f"refused: install-class command {_ask_name!r} needs "
                "install permission (ungranted runs continue without "
                "the install)")
        if not _ask_project_grant and not _ask_run_allow:
            # FXR4A D4: the once-allow is spent by an earlier run; the
            # next run asks again, never silently refuses.
            with contextlib.suppress(Exception):
                _ask_permissions.record_install_request(
                    tool_id=_ask_tool_id,
                    argv=list(words),
                    project_id=str(project_id))
            raise InstallAskNeeded(
                _ask_tool_id,
                f"refused: install-class command {words[0]!r} needs "
                "install permission (an earlier allow is spent; "
                "ungranted runs continue without the install)")
        _ask_approved = (
            [str(word) for word in words]
            if _ask_project_grant
            else _ask_permissions.get_install_argv(
                tool_id=_ask_tool_id))
        if _ask_approved is None:
            with contextlib.suppress(Exception):
                _ask_approved = _ask_permissions.pin_install_argv(
                    tool_id=_ask_tool_id,
                    argv=list(words),
                    project_id=str(project_id))
        if _ask_approved is not None and [
                str(word) for word in _ask_approved] != words:
            # FXR4A D5: different exact words are a new ask with the
            # real words, never a silent no-op into checks-green
            # success. The pin moves to what is actually asked about
            # (denies are never touched), so an allow covers it.
            with contextlib.suppress(Exception):
                _ask_permissions.repin_install_request(
                    tool_id=_ask_tool_id,
                    argv=list(words),
                    project_id=str(project_id))
            raise InstallAskNeeded(
                _ask_tool_id,
                f"refused: install-class command {words[0]!r} needs "
                "install permission for these exact words "
                f"{words!r} (an approval runs these exact words only)")
        if not _ask_project_grant:
            # FXR4A D4: the replay consumes the once-allow; the next
            # run asks again. Best effort: a consume failure never
            # blocks the allowed spawn.
            with contextlib.suppress(Exception):
                _ask_permissions.note_decision_consumed(
                    tool_id=_ask_tool_id, run_id=_ask_scope)
    if kind == "inline":
        raise PermissionError(
            "refused: inline code needs approval first "
            "(unapproved runs continue without it)")
    missing = _missing_head(words, str(folder))
    if missing is not None:
        raise SpawnNotInstalled(missing)
    words = _windows_findstr_files(words)
    job: dict[str, Any] = {
        "project_id": str(project_id),
        "check_run_id": str(run_id),
        "log_path": str(log_path),
        "log_rel": str(log_rel),
    }
    parent = os.path.dirname(log_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with _retry_av_lock(lambda: open(log_path, "wb")):
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
        # lifts for these exact words only. The carried argv comes from
        # the ledger pin (ask-time request, or the first allowed spawn),
        # never rebuilt from the current words, so the guard exact-match
        # stays live on this path too. Shell-fragment, widening and
        # path checks still run; nothing else changes.
        _ask_carry = (_ask_approved if _ask_approved is not None
                      else list(words))
        auth["install_approved"] = True
        auth["install_argv"] = [str(word) for word in _ask_carry]
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
    """Terminate then tree-kill one child; never raises."""
    from agent_si.backend import proc_tree as _proc_tree

    with contextlib.suppress(Exception):
        _proc_tree.terminate_tree(proc)


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
                from agent_si.backend import proc_tree as _proc_tree

                proc.wait(timeout=_proc_tree.STOP_TIMEOUT_S)
            return
        _kill(proc)
    with contextlib.suppress(Exception):
        from agent_si.backend import proc_tree as _proc_tree

        proc.wait(timeout=_proc_tree.STOP_TIMEOUT_S)


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
    text = _decode_console_text(blob)
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
