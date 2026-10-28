"""K06 Lane A toolguard -- G1 guard entry point.

Argv-only evaluation: ``argv`` must be a list of words; a shell
string is refused and named. Installer and fetch commands are
refused by name (auto-install stays off: nothing is ever fetched
or installed here); unknown bare tool names pass this layer and
are refused at the dispatch seam, which owns the registry. Every
path argument is canonicalized with realpath plus normcase before
comparison, so paths outside the workspace root are refused under
every spelling while the reported value keeps its original
backslashes. Loopback, link-local, unspecified, private and
otherwise internal hosts are refused in fetch arguments, and
privilege-widening flags are refused by name. Permission failures
deny with the exact error code; passes allow R0/R1 and return a
review card for R2/R3. Verdicts are plain data, never
instructions.
"""

from __future__ import annotations

import importlib
import importlib.util
import ipaddress
import os
from typing import Any
from urllib.parse import urlsplit

ACTION_CLASSES: tuple[str, ...] = ("R0", "R1", "R2", "R3")

DECISIONS: tuple[str, ...] = ("allow", "ask", "deny")

_INSTALLER_COMMANDS = frozenset(
    {
        "pip",
        "pip3",
        "pipx",
        "npm",
        "npx",
        "yarn",
        "pnpm",
        "bun",
        "conda",
        "mamba",
        "micromamba",
        "poetry",
        "uv",
        "pdm",
        "apt",
        "apt-get",
        "apk",
        "dnf",
        "yum",
        "brew",
        "choco",
        "winget",
        "scoop",
        "curl",
        "wget",
        "aria2c",
        "gem",
        "nuget",
        "cabal",
        "composer",
    }
)

_FETCH_COMMANDS = frozenset(
    {
        "fetch",
        "curl",
        "wget",
        "http",
        "https",
        "get",
        "download",
        "downloads",
        "invoke-webrequest",
        "iwr",
    }
)

_WIDENING_FLAGS_EXACT = frozenset(
    {
        "--allow-all",
        "--allowall",
        "--allow-root",
        "--allow-unsafe",
        "--as-root",
        "--run-as-root",
        "--runas-root",
        "--privileged",
        "--unsafe",
        "--insecure",
        "--bypass",
        "--elevate",
        "--widen",
        "--admin",
        "--sudo",
        "--setuid",
        "--setgid",
        "--impersonate",
        "--system",
        "--no-sandbox",
        "--disable-signature-check",
    }
)

_WIDENING_FLAG_PREFIXES = (
    "--privileged",
    "--bypass",
    "--unsafe",
    "--insecure",
    "--no-sandbox",
    "--disable-sandbox",
    "--no-verify",
    "--no-verification",
    "--skip-verify",
    "--skip-verification",
    "--allow-root",
    "--run-as-root",
    "--elevate",
    "--widen",
    "--admin",
    "--sudo",
    "--setuid",
    "--setgid",
    "--impersonate",
    "--as-root",
    "--runas",
)

_SHELL_FRAGMENTS = (";", "|", "&", "`", "$", "\n", "\r", "\0")

_INTERNAL_NAMES = frozenset(
    {
        "localhost",
        "metadata.google.internal",
        "host.docker.internal",
        "gateway.docker.internal",
        "instance-data",
        "wpad",
    }
)

_INTERNAL_SUFFIXES = (".localhost", ".internal", ".local")

_SIBLINGS: dict[str, Any] = {}


def _sibling(name: str) -> Any:
    """Return a toolguard sibling module without a static import."""
    if name not in _SIBLINGS:
        try:
            _SIBLINGS[name] = importlib.import_module("agent_si.toolguard." + name)
        except ImportError:
            path = os.path.join(os.path.dirname(os.path.realpath(__file__)), name + ".py")
            spec = importlib.util.spec_from_file_location("agent_si_toolguard_" + name, path)
            if spec is None or spec.loader is None:
                raise ImportError("cannot locate toolguard module: " + name)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            _SIBLINGS[name] = module
    return _SIBLINGS[name]


def _canon(path: str) -> str:
    """Canonical path key: realpath plus normcase for every comparison."""
    return os.path.normcase(os.path.realpath(path))


def _workspace_root() -> str:
    """Canonical workspace root this evaluation is anchored at."""
    return _canon(os.getcwd())


def _under_root(canonical: str, root: str) -> bool:
    """True when a canonical path sits at or under the canonical root."""
    return canonical == root or canonical.startswith(root + os.sep)


def _looks_like_path(value: str) -> bool:
    """True when a value has path shape (never applied to bare words)."""
    if not value or value == "-":
        return False
    if os.path.isabs(value):
        return True
    if "/" in value or "\\" in value:
        return True
    if value in (".", ".."):
        return True
    for prefix in ("../", "..\\", "./", ".\\", "~/"):
        if value.startswith(prefix):
            return True
    if len(value) >= 2 and value[0].isalpha() and value[1] == ":":
        return True
    return False


def _command_name(tool: str) -> str:
    """Bare command name, lowercased, without directories or suffix."""
    base = tool.replace("\\", "/").rsplit("/", 1)[-1].lower()
    for suffix in (".exe", ".bat", ".cmd", ".com"):
        if base.endswith(suffix) and len(base) > len(suffix):
            base = base[: -len(suffix)]
    return base


def _has_shell_fragment(value: str) -> bool:
    """True when a word carries characters only a shell would act on."""
    return any(fragment in value for fragment in _SHELL_FRAGMENTS)


def _url_host(value: str) -> str | None:
    """Extract the host from a URL value; None when it has none."""
    try:
        host = urlsplit(value).hostname
    except ValueError:
        host = None
    if host:
        return host
    after = value.split("://", 1)[1]
    after = after.split("/", 1)[0].split("?", 1)[0].split("#", 1)[0]
    if "@" in after:
        after = after.rsplit("@", 1)[1]
    if after.startswith("["):
        return after.split("]", 1)[0][1:] or None
    if after.count(":") == 1:
        after = after.split(":", 1)[0]
    return after or None


def _bare_host(value: str) -> str | None:
    """Extract a bare host token; None for flags, empty or path values."""
    text = value.strip()
    if not text or text.startswith("-") or " " in text or "://" in text:
        return None
    for sep in ("/", "?", "#"):
        if sep in text:
            text = text.split(sep, 1)[0]
    if "@" in text:
        text = text.rsplit("@", 1)[1]
    if text.startswith("["):
        return text.split("]", 1)[0][1:] or None
    if text.count(":") == 1:
        head, _, tail = text.partition(":")
        if not tail.isdigit():
            return None
        text = head
    elif ":" in text:
        return None
    return text or None


def _is_internal_host(host: str) -> bool:
    """True for loopback, link-local, unspecified, private or LAN names."""
    name = host.strip().lower().rstrip(".")
    if not name:
        return False
    if name in _INTERNAL_NAMES:
        return True
    if any(name.endswith(suffix) for suffix in _INTERNAL_SUFFIXES):
        return True
    try:
        address = ipaddress.ip_address(name)
    except ValueError:
        return False
    if getattr(address, "ipv4_mapped", None) is not None:
        mapped = address.ipv4_mapped
        if mapped is not None and (
            mapped.is_loopback
            or mapped.is_link_local
            or mapped.is_private
            or mapped.is_unspecified
        ):
            return True
    return (
        address.is_loopback
        or address.is_link_local
        or address.is_private
        or address.is_unspecified
    )


def _deny(reason: str, action_class: Any, tool_label: str) -> dict[str, Any]:
    """Build a deny verdict with a stable evidence reference."""
    label = str(tool_label)[:40] if tool_label else "none"
    return {
        "decision": "deny",
        "reason": reason,
        "evidence_ref": "toolguard:deny:%s:%s" % (action_class, label),
    }


def evaluate(
    argv: list[str],
    action_class: str,
    auth: dict[str, Any],
) -> dict[str, Any]:
    """Evaluate ``argv`` for ``action_class`` under ``auth``.

    Returns a verdict dict with decision (allow, ask or deny),
    a human-readable reason and an evidence reference. Dangerous
    shapes are refused before any permission lookup; permission
    failures deny with the exact error code.
    """
    if isinstance(argv, (str, bytes, bytearray)):
        if isinstance(argv, (bytes, bytearray)):
            shown = bytes(argv).decode("utf-8", "replace")[:120]
        else:
            shown = argv[:120]
        return _deny(
            "argv must be a list of words, never a shell string: %r" % (shown,),
            action_class,
            "non-list",
        )
    try:
        words = list(argv)
    except TypeError:
        return _deny(
            "argv must be a list of words, never a shell string: %s"
            % (type(argv).__name__,),
            action_class,
            "non-list",
        )
    for item in words:
        if not isinstance(item, str):
            return _deny(
                "argv must be a list of words (non-str element: %s)"
                % (type(item).__name__,),
                action_class,
                "non-list",
            )
    if not words:
        return _deny("argv must not be empty", action_class, "empty")
    for item in words:
        if _has_shell_fragment(item):
            return _deny(
                "refused: shell metacharacters in argv element: %r" % (item,),
                action_class,
                words[0],
            )
    tool = words[0]
    name = _command_name(tool)
    fetch_like = name in _FETCH_COMMANDS
    for item in words[1:]:
        candidate = item
        if item.startswith("-") and "=" in item:
            candidate = item.split("=", 1)[1]
        host = None
        if "://" in candidate:
            host = _url_host(candidate)
        elif fetch_like and not item.startswith("-"):
            host = _bare_host(candidate)
        if host is not None and _is_internal_host(host):
            return _deny(
                "refused: internal address in fetch argument, host %r" % (host,),
                action_class,
                tool,
            )
    for item in words[1:]:
        if not item.startswith("-") or item == "-":
            continue
        flag = item.split("=", 1)[0].lower()
        if flag in _WIDENING_FLAGS_EXACT or flag.startswith(_WIDENING_FLAG_PREFIXES):
            return _deny(
                "refused: privilege-widening flag: %s" % (item,),
                action_class,
                tool,
            )
    root = _workspace_root()
    if _looks_like_path(tool) and not _under_root(_canon(tool), root):
        return _deny(
            "refused: path outside the workspace root: %s" % (tool,),
            action_class,
            tool,
        )
    for item in words[1:]:
        values = [item]
        if item.startswith("-") and "=" in item:
            values.append(item.split("=", 1)[1])
        for value in values:
            if "://" in value or value.startswith("-") or not _looks_like_path(value):
                continue
            if not _under_root(_canon(value), root):
                return _deny(
                    "refused: path outside the workspace root: %s" % (value,),
                    action_class,
                    tool,
                )
    if name in _INSTALLER_COMMANDS:
        return _deny(
            "refused: installer and fetch commands are disabled "
            "(auto-install off), unknown tool %r" % (tool,),
            action_class,
            tool,
        )
    generated = bool(auth.get("generated", False)) if isinstance(auth, dict) else False
    check_permission = _sibling("permissions").check_permission
    verdict = check_permission(action_class, auth, generated)
    if isinstance(verdict, dict) and "error" in verdict:
        return _deny(str(verdict["error"]), action_class, tool)
    if action_class in ("R0", "R1"):
        return {
            "decision": "allow",
            "reason": "allowed: %s authorized for tool %r" % (action_class, tool),
            "evidence_ref": "toolguard:allow:%s:%s" % (action_class, name[:40]),
        }
    ask_module = _sibling("ask")
    card = ask_module.build_ask_card(
        ask_id="ask-%s-%s" % (action_class, name[:40]),
        kind="approve",
        summary="action awaiting approval: tool %r (%s)" % (tool, action_class),
        options=["approve", "deny"],
        resume_token="resume-%s-%s" % (action_class, name[:40]),
    )
    return {
        "decision": "ask",
        "reason": "action requires approval: %s" % (action_class,),
        "evidence_ref": "toolguard:ask:%s:%s" % (action_class, name[:40]),
        "ask_card": card,
    }
